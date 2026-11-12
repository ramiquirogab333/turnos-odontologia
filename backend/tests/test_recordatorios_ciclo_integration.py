"""C-09 (4.4-4.6): reconciliación, proveedor con reintentos y ausencia de datos personales en el ciclo. Datos sintéticos."""

import logging
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.notificaciones.proveedor import ErrorTransitorioProveedor, ProveedorFalso, ProveedorManual
from tests.panel_helpers import insertar_turno, sembrar_mundo
from tests.recordatorios_helpers import AHORA, ciclo, poner_turno, recordatorios, sembrar_recordatorio

Factory = async_sessionmaker[AsyncSession]


# --- 4.4 Reconciliación -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("estado", ["pendiente", "enviado", "fallido", "confirmado"])
async def test_un_turno_cancelado_anula_sus_recordatorios_vigentes(session_factory: Factory, estado: str) -> None:
    mundo = await sembrar_mundo(session_factory)
    inicio = AHORA + timedelta(hours=30)
    turno = await insertar_turno(session_factory, mundo, inicio, estado="cancelado")
    await sembrar_recordatorio(session_factory, turno, inicio, estado)
    await ciclo(session_factory)
    [r] = await recordatorios(session_factory, turno)
    assert (r.estado, r.motivo, r.confirmado_en, r.proximo_intento_en) == ("anulado", "turno_cancelado", None, None)


async def test_un_turno_reprogramado_anula_el_del_horario_anterior_y_genera_uno_nuevo(session_factory: Factory) -> None:
    mundo = await sembrar_mundo(session_factory)
    viejo = AHORA + timedelta(hours=30)
    nuevo = AHORA + timedelta(hours=40)
    turno = await insertar_turno(session_factory, mundo, nuevo)
    await sembrar_recordatorio(session_factory, turno, viejo, "enviado")
    resumen = await ciclo(session_factory)
    r1, r2 = await recordatorios(session_factory, turno)
    assert (r1.estado, r1.motivo, r1.turno_inicio) == ("anulado", "turno_reprogramado", viejo)
    assert (r2.estado, r2.turno_inicio) == ("pendiente", nuevo)
    assert (resumen.reconciliados, resumen.generados) == (1, 1)


async def test_un_confirmado_del_horario_vigente_no_se_toca(session_factory: Factory) -> None:
    mundo = await sembrar_mundo(session_factory)
    inicio = AHORA + timedelta(hours=30)
    turno = await insertar_turno(session_factory, mundo, inicio, estado="confirmado")
    rid = await sembrar_recordatorio(session_factory, turno, inicio, "confirmado")
    resumen = await ciclo(session_factory)
    [r] = await recordatorios(session_factory, turno)
    assert (r.id, r.estado, resumen.reconciliados) == (rid, "confirmado", 0)


@pytest.mark.parametrize("estado_turno", ["ausente", "atendido"])
async def test_un_turno_atendido_o_ausente_conserva_el_historial_del_recordatorio(
        session_factory: Factory, estado_turno: str) -> None:
    mundo = await sembrar_mundo(session_factory)
    inicio = AHORA - timedelta(hours=2)
    turno = await insertar_turno(session_factory, mundo, inicio, estado=estado_turno)
    await sembrar_recordatorio(session_factory, turno, inicio, "enviado")
    await ciclo(session_factory)
    assert [r.estado for r in await recordatorios(session_factory, turno)] == ["enviado"]


async def test_un_turno_que_vuelve_a_un_horario_anulado_obtiene_un_recordatorio_nuevo(session_factory: Factory) -> None:
    mundo = await sembrar_mundo(session_factory)
    inicio = AHORA + timedelta(hours=30)
    turno = await insertar_turno(session_factory, mundo, inicio)
    await sembrar_recordatorio(session_factory, turno, inicio, "anulado", motivo="turno_reprogramado")
    await ciclo(session_factory)
    assert [r.estado for r in await recordatorios(session_factory, turno)] == ["anulado", "pendiente"]


# --- 4.5 Proveedor y reintentos ---------------------------------------------------------------------------------

async def test_el_proveedor_manual_deja_el_recordatorio_pendiente_con_cero_intentos(session_factory: Factory) -> None:
    mundo = await sembrar_mundo(session_factory)
    turno = await insertar_turno(session_factory, mundo, AHORA + timedelta(hours=30))
    resumen = await ciclo(session_factory, proveedor=ProveedorManual())
    [r] = await recordatorios(session_factory, turno)
    assert (r.estado, r.intentos_fallidos, r.proximo_intento_en, r.enviado_en) == ("pendiente", 0, None, None)
    assert resumen.procesados == 1


async def test_un_proveedor_que_falla_siempre_reintenta_a_1_5_y_15_minutos_y_deja_fallido(
        session_factory: Factory) -> None:
    mundo = await sembrar_mundo(session_factory)
    turno = await insertar_turno(session_factory, mundo, AHORA + timedelta(hours=30))
    proveedor = ProveedorFalso([ErrorTransitorioProveedor("sin conexion")])
    esperado = [(1, timedelta(minutes=1)), (2, timedelta(minutes=5)), (3, timedelta(minutes=15))]
    ahora = AHORA
    await ciclo(session_factory, ahora=ahora, proveedor=proveedor)
    for intentos, espera in esperado:
        [r] = await recordatorios(session_factory, turno)
        assert (r.estado, r.intentos_fallidos, r.proximo_intento_en) == ("pendiente", intentos, ahora + espera)
        # Antes de la hora de reintento no se vuelve a llamar al proveedor.
        llamadas = proveedor.llamadas
        await ciclo(session_factory, ahora=ahora + espera - timedelta(seconds=1), proveedor=proveedor)
        assert proveedor.llamadas == llamadas
        ahora = ahora + espera
        await ciclo(session_factory, ahora=ahora, proveedor=proveedor)
    [r] = await recordatorios(session_factory, turno)
    assert (r.estado, r.motivo, r.intentos_fallidos, r.proximo_intento_en) == ("fallido", "error_proveedor", 4, None)
    assert r.ultimo_error is not None and "ErrorTransitorioProveedor" in r.ultimo_error
    assert proveedor.llamadas == 4  # el intento inicial y los tres reintentos
    await ciclo(session_factory, ahora=ahora + timedelta(hours=1), proveedor=proveedor)
    assert proveedor.llamadas == 4  # fallido no se reintenta más


async def test_un_proveedor_que_falla_una_vez_y_luego_responde_conserva_un_intento_fallido(
        session_factory: Factory) -> None:
    mundo = await sembrar_mundo(session_factory)
    turno = await insertar_turno(session_factory, mundo, AHORA + timedelta(hours=30))
    proveedor = ProveedorFalso([ErrorTransitorioProveedor("timeout"), "enviado"])
    await ciclo(session_factory, proveedor=proveedor)
    await ciclo(session_factory, ahora=AHORA + timedelta(minutes=1), proveedor=proveedor)
    [r] = await recordatorios(session_factory, turno)
    assert (r.estado, r.intentos_fallidos, r.proximo_intento_en, r.enviado_en) == (
        "enviado", 1, None, AHORA + timedelta(minutes=1))
    assert r.enviado_por_usuario_id is None


async def test_un_proveedor_que_pide_accion_manual_tras_un_error_vuelve_a_quedar_pendiente_sin_reintento(
        session_factory: Factory) -> None:
    mundo = await sembrar_mundo(session_factory)
    turno = await insertar_turno(session_factory, mundo, AHORA + timedelta(hours=30))
    proveedor = ProveedorFalso([ErrorTransitorioProveedor("timeout"), "requiere_accion_manual"])
    await ciclo(session_factory, proveedor=proveedor)
    await ciclo(session_factory, ahora=AHORA + timedelta(minutes=1), proveedor=proveedor)
    [r] = await recordatorios(session_factory, turno)
    assert (r.estado, r.intentos_fallidos, r.proximo_intento_en) == ("pendiente", 1, None)


# --- 4.6 Sin datos personales -----------------------------------------------------------------------------------

async def test_un_error_del_proveedor_con_un_telefono_no_queda_en_la_base_ni_en_el_log(
        session_factory: Factory, caplog: pytest.LogCaptureFixture) -> None:
    mundo = await sembrar_mundo(session_factory)
    turno = await insertar_turno(session_factory, mundo, AHORA + timedelta(hours=30))
    proveedor = ProveedorFalso([ErrorTransitorioProveedor(
        "rechazo para +5491100000003 (lucia@ejemplo.test) en https://api.ficticia.test/m?t=+5491100000003")])
    with caplog.at_level(logging.DEBUG):
        await ciclo(session_factory, proveedor=proveedor)
    [r] = await recordatorios(session_factory, turno)
    assert r.ultimo_error is not None and len(r.ultimo_error) <= 500
    for dato in ("5491100000003", "lucia@ejemplo.test", "api.ficticia.test"):
        assert dato not in r.ultimo_error
        assert dato not in caplog.text


async def test_el_log_de_un_ciclo_con_50_turnos_solo_tiene_cantidades(
        session_factory: Factory, caplog: pytest.LogCaptureFixture) -> None:
    mundo = await sembrar_mundo(session_factory, franja=("00:00", "23:59"), duracion=15)
    nombres = []
    for i in range(50):
        nombre = f"Paciente Ficticio {i:02d}"
        nombres.append(nombre)
        await insertar_turno(session_factory, mundo, AHORA + timedelta(hours=1, minutes=15 * i), nombre=nombre,
                             telefono=f"+54911000001{i:02d}", minutos=15)
    with caplog.at_level(logging.DEBUG):
        resumen = await ciclo(session_factory)
    assert resumen.generados == 50
    registros = [r.getMessage() for r in caplog.records if r.name.startswith("app.notificaciones")]
    assert registros and any("generados=50" in m for m in registros)
    texto = "\n".join(registros)
    assert "wa.me" not in texto and "confirmar#" not in texto
    for nombre in nombres[:3]:
        assert nombre not in texto
    assert "+54911000001" not in texto


async def test_el_mensaje_no_se_guarda_en_la_tabla(session_factory: Factory) -> None:
    from app.notificaciones.models import Recordatorio

    columnas = set(Recordatorio.__table__.c.keys())
    assert not columnas & {"mensaje", "texto", "link", "telefono", "nombre", "codigo_gestion"}
