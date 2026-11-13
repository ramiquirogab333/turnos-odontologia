"""C-10 (8.1-8.4): conflictos con Google Calendar, cierre automático y resolución manual. Sintético (R19)."""

from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integraciones.gcal.proveedor_falso import ProveedorFalso
from app.models.core import RegistroAuditoria
from tests.conftest import bearer, crear_usuario_panel
from tests.gcal_helpers import AHORA, ciclo, conflictos, eventos, sembrar_conexion
from tests.panel_helpers import insertar_turno, sembrar_mundo, turno as cargar_turno
from tests.recordatorios_helpers import poner_turno

Factory = async_sessionmaker[AsyncSession]
MANANA = AHORA + timedelta(days=1)
M30 = timedelta(minutes=30)
BASE = "/api/panel/google-calendar"


async def _con_evento(factory: Factory, proveedor: ProveedorFalso, **campos) -> tuple[dict[str, int], int, int, str]:
    mundo = await sembrar_mundo(factory)
    conexion = await sembrar_conexion(factory, mundo["ana"])
    turno = await insertar_turno(factory, mundo, campos.pop("inicio", MANANA), **campos)
    await ciclo(factory, proveedor)
    [vinculo] = [e for e in await eventos(factory, conexion) if e.origen == "sistema"]
    return mundo, conexion, turno, vinculo.google_event_id


# --- 8.1 Un cambio en Google nunca modifica un turno --------------------------------------------------------------

async def test_mover_el_evento_en_google_deja_el_turno_igual_y_abre_un_conflicto_con_ambos_horarios(
        session_factory: Factory, proveedor_gcal: ProveedorFalso) -> None:
    _, _, turno, evento = await _con_evento(session_factory, proveedor_gcal)
    nuevo = MANANA + timedelta(hours=2)
    proveedor_gcal.mover(evento, nuevo, nuevo + M30)
    await ciclo(session_factory, proveedor_gcal)
    [c] = await conflictos(session_factory)
    assert (c.tipo, c.estado, c.turno_id) == ("movido_en_google", "abierto", turno)
    assert (c.sistema_inicio, c.sistema_fin, c.google_inicio, c.google_fin) == (MANANA, MANANA + M30, nuevo, nuevo + M30)
    t = await cargar_turno(session_factory, turno)
    assert (t.inicio, t.estado) == (MANANA, "reservado")
    assert proveedor_gcal.vigentes()[0].inicio == nuevo  # el sistema no reescribe el evento
    await ciclo(session_factory, proveedor_gcal)
    assert len(await conflictos(session_factory)) == 1  # sin duplicados en ciclos siguientes


async def test_borrar_el_evento_en_google_abre_un_conflicto_y_no_lo_recrea(session_factory: Factory,
                                                                          proveedor_gcal: ProveedorFalso) -> None:
    _, _, turno, evento = await _con_evento(session_factory, proveedor_gcal, estado="confirmado")
    proveedor_gcal.borrar_externo(evento)
    for _ in range(2):
        await ciclo(session_factory, proveedor_gcal)
    [c] = await conflictos(session_factory)
    assert (c.tipo, c.google_inicio) == ("borrado_en_google", None)
    assert (await cargar_turno(session_factory, turno)).estado == "confirmado"
    assert proveedor_gcal.llamadas.count("insertar") == 1 and proveedor_gcal.vigentes() == []


async def test_editar_solo_el_titulo_en_google_no_es_conflicto_ni_se_reescribe(session_factory: Factory,
                                                                               proveedor_gcal: ProveedorFalso) -> None:
    _, _, _, evento = await _con_evento(session_factory, proveedor_gcal)
    proveedor_gcal.editar_titulo(evento, "Mi título")
    await ciclo(session_factory, proveedor_gcal)
    assert await conflictos(session_factory) == []
    assert proveedor_gcal.vigentes()[0].titulo == "Mi título" and proveedor_gcal.llamadas.count("actualizar") == 0


async def test_si_cambian_los_dos_lados_gana_el_conflicto_y_no_se_escribe(session_factory: Factory,
                                                                          proveedor_gcal: ProveedorFalso) -> None:
    _, _, turno, evento = await _con_evento(session_factory, proveedor_gcal)
    en_google = MANANA + timedelta(hours=2)
    proveedor_gcal.mover(evento, en_google, en_google + M30)
    await poner_turno(session_factory, turno, inicio=MANANA + timedelta(hours=5), fin=MANANA + timedelta(hours=5, minutes=30))
    await ciclo(session_factory, proveedor_gcal)
    [c] = await conflictos(session_factory)
    assert c.tipo == "movido_en_google" and c.sistema_inicio == MANANA + timedelta(hours=5)
    assert proveedor_gcal.llamadas.count("actualizar") == 0 and proveedor_gcal.vigentes()[0].inicio == en_google


async def test_devolver_el_evento_al_horario_del_turno_cierra_el_conflicto_solo(session_factory: Factory,
                                                                                proveedor_gcal: ProveedorFalso) -> None:
    _, _, _, evento = await _con_evento(session_factory, proveedor_gcal)
    proveedor_gcal.mover(evento, MANANA + timedelta(hours=2), MANANA + timedelta(hours=2, minutes=30))
    await ciclo(session_factory, proveedor_gcal)
    proveedor_gcal.mover(evento, MANANA, MANANA + M30)
    await ciclo(session_factory, proveedor_gcal)
    [c] = await conflictos(session_factory)
    assert (c.estado, c.resolucion, c.resuelto_por_usuario_id) == ("resuelto", "solape_desaparecido", None)


# --- 8.2 Solapes y cierre automático ------------------------------------------------------------------------------

async def test_una_sena_acreditada_sobre_una_franja_ocupada_abre_solapa_evento_externo(
        session_factory: Factory, proveedor_gcal: ProveedorFalso) -> None:
    mundo = await sembrar_mundo(session_factory)
    conexion = await sembrar_conexion(session_factory, mundo["ana"])
    turno = await insertar_turno(session_factory, mundo, MANANA, estado="en_espera", vence=MANANA)
    proveedor_gcal.crear_ocupado(MANANA, MANANA + timedelta(hours=1))
    await ciclo(session_factory, proveedor_gcal)
    assert await conflictos(session_factory) == []  # la pre-reserva no bloquea agenda (R8)
    await poner_turno(session_factory, turno, estado="reservado", en_espera_vence_en=None)  # se acredita la seña
    await ciclo(session_factory, proveedor_gcal)
    [c] = await conflictos(session_factory)
    assert (c.tipo, c.turno_id, c.sistema_inicio, c.google_inicio, c.google_fin) == (
        "solapa_evento_externo", turno, MANANA, MANANA, MANANA + timedelta(hours=1))
    assert len(proveedor_gcal.vigentes("primary")) == 2  # el ajeno y el evento del turno
    await ciclo(session_factory, proveedor_gcal)
    assert len(await conflictos(session_factory)) == 1


async def test_los_intervalos_que_solo_se_tocan_en_el_borde_no_son_conflicto(session_factory: Factory,
                                                                             proveedor_gcal: ProveedorFalso) -> None:
    mundo = await sembrar_mundo(session_factory)
    await sembrar_conexion(session_factory, mundo["ana"])
    await insertar_turno(session_factory, mundo, MANANA)  # [MANANA, MANANA+30)
    proveedor_gcal.crear_ocupado(MANANA + M30, MANANA + timedelta(hours=1, minutes=30))  # empieza cuando termina
    proveedor_gcal.crear_ocupado(MANANA - timedelta(hours=1), MANANA)  # termina cuando empieza
    await ciclo(session_factory, proveedor_gcal)
    assert await conflictos(session_factory) == []


async def test_el_alta_manual_sobre_una_franja_queda_en_conflicto_tras_el_ciclo(session_factory: Factory,
                                                                                proveedor_gcal: ProveedorFalso) -> None:
    mundo = await sembrar_mundo(session_factory)
    await sembrar_conexion(session_factory, mundo["ana"])
    proveedor_gcal.crear_ocupado(MANANA, MANANA + timedelta(hours=1))
    await ciclo(session_factory, proveedor_gcal)
    await insertar_turno(session_factory, mundo, MANANA, origen="manual")
    await ciclo(session_factory, proveedor_gcal)
    assert [c.tipo for c in await conflictos(session_factory, "abierto")] == ["solapa_evento_externo"]


async def test_cancelar_el_turno_cierra_sus_conflictos_con_turno_cancelado(session_factory: Factory,
                                                                           proveedor_gcal: ProveedorFalso) -> None:
    _, _, turno, evento = await _con_evento(session_factory, proveedor_gcal)
    proveedor_gcal.mover(evento, MANANA + timedelta(hours=2), MANANA + timedelta(hours=2, minutes=30))
    await ciclo(session_factory, proveedor_gcal)
    await poner_turno(session_factory, turno, estado="cancelado")
    await ciclo(session_factory, proveedor_gcal)
    [c] = await conflictos(session_factory)
    assert (c.estado, c.resolucion, c.resuelto_por_usuario_id) == ("resuelto", "turno_cancelado", None)
    assert proveedor_gcal.vigentes() == []  # y el evento (movido) se borra en el mismo ciclo


async def test_cancelar_un_turno_cuyo_evento_ya_no_esta_en_google_no_llama_a_google(
        session_factory: Factory, proveedor_gcal: ProveedorFalso) -> None:
    _, conexion, turno, evento = await _con_evento(session_factory, proveedor_gcal)
    proveedor_gcal.borrar_externo(evento)
    await ciclo(session_factory, proveedor_gcal)
    llamadas = list(proveedor_gcal.llamadas)
    await poner_turno(session_factory, turno, estado="cancelado")
    await ciclo(session_factory, proveedor_gcal)
    nuevas = proveedor_gcal.llamadas[len(llamadas):]
    assert [m for m in nuevas if m in ("insertar", "actualizar", "borrar")] == []
    [c] = await conflictos(session_factory)
    assert (c.resolucion, c.resuelto_por_usuario_id) == ("turno_cancelado", None)
    assert [e.estado for e in await eventos(session_factory, conexion)] == ["borrado"]


@pytest.mark.parametrize("accion", ["mover", "borrar", "libre"])
async def test_si_la_franja_se_mueve_afuera_se_borra_o_pasa_a_libre_el_solape_se_cierra_solo(
        session_factory: Factory, proveedor_gcal: ProveedorFalso, accion: str) -> None:
    mundo = await sembrar_mundo(session_factory)
    await sembrar_conexion(session_factory, mundo["ana"])
    await insertar_turno(session_factory, mundo, MANANA)
    franja = proveedor_gcal.crear_ocupado(MANANA, MANANA + timedelta(hours=1))
    await ciclo(session_factory, proveedor_gcal)
    assert len(await conflictos(session_factory, "abierto")) == 1
    if accion == "mover":
        proveedor_gcal.mover(franja, MANANA + timedelta(hours=3), MANANA + timedelta(hours=4))
    elif accion == "borrar":
        proveedor_gcal.borrar_externo(franja)
    else:
        proveedor_gcal.eventos[("primary", franja)].ocupa = False
        proveedor_gcal.mover(franja, MANANA, MANANA + timedelta(hours=1))
    await ciclo(session_factory, proveedor_gcal)
    [c] = await conflictos(session_factory)
    assert (c.estado, c.resolucion) == ("resuelto", "solape_desaparecido")


# --- 8.4 Resolución manual ----------------------------------------------------------------------------------------

async def _movido(factory: Factory, proveedor: ProveedorFalso):
    mundo, conexion, turno, evento = await _con_evento(factory, proveedor)
    proveedor.mover(evento, MANANA + timedelta(hours=2), MANANA + timedelta(hours=2, minutes=30))
    await ciclo(factory, proveedor)
    [c] = await conflictos(factory)
    return mundo, conexion, turno, evento, c


async def test_el_listado_trae_ambos_horarios_el_criterio_y_las_acciones_por_rol(
        client: AsyncClient, session_factory: Factory, proveedor_gcal: ProveedorFalso, token_recepcion: str) -> None:
    mundo, _, turno, _, c = await _movido(session_factory, proveedor_gcal)
    _, token_odonto = await crear_usuario_panel(session_factory, "ana.odonto@example.com", ["odontologo"],
                                                profesional_id=mundo["ana"])
    r = await client.get(f"{BASE}/conflictos", headers=bearer(token_recepcion))
    [item] = r.json()
    assert (item["id"], item["tipo"], item["turno_id"]) == (c.id, "movido_en_google", turno)
    assert item["acciones"] == ["restaurar_en_google", "desvincular"] and "movió" in item["criterio"]
    assert item["sistema_inicio"].startswith("2026-11-17T09:00") and item["google_inicio"].startswith("2026-11-17T11:00")
    assert item["tratamiento"] == "Limpieza dental" and "paciente" not in "".join(item).lower().replace("pacientes", "")
    propio = (await client.get(f"{BASE}/conflictos", headers=bearer(token_odonto))).json()
    assert [i["id"] for i in propio] == [c.id] and propio[0]["acciones"] == []
    assert (await client.get(f"{BASE}/conflictos")).status_code == 401


async def test_restaurar_en_google_un_evento_movido_lo_devuelve_en_el_ciclo_siguiente(
        client: AsyncClient, session_factory: Factory, proveedor_gcal: ProveedorFalso, token_recepcion: str) -> None:
    _, _, _, _, c = await _movido(session_factory, proveedor_gcal)
    r = await client.post(f"{BASE}/conflictos/{c.id}/resolver", json={"accion": "restaurar_en_google"},
                          headers=bearer(token_recepcion))
    assert r.status_code == 200 and (r.json()["estado"], r.json()["resolucion"]) == ("resuelto", "restaurar_en_google")
    assert proveedor_gcal.vigentes()[0].inicio == MANANA + timedelta(hours=2)  # todavía no se escribió
    await ciclo(session_factory, proveedor_gcal)
    assert proveedor_gcal.vigentes()[0].inicio == MANANA
    async with session_factory() as s:
        auditoria = (await s.execute(select(RegistroAuditoria).where(
            RegistroAuditoria.entidad == "gcal_conflicto"))).scalars().all()
    assert len(auditoria) == 1 and "Carlos" not in str(auditoria[0].datos_despues)


async def test_restaurar_un_evento_borrado_crea_uno_nuevo_con_otra_generacion(
        client: AsyncClient, session_factory: Factory, proveedor_gcal: ProveedorFalso, token_recepcion: str) -> None:
    _, conexion, turno, evento = await _con_evento(session_factory, proveedor_gcal)
    proveedor_gcal.borrar_externo(evento)
    await ciclo(session_factory, proveedor_gcal)
    [c] = await conflictos(session_factory)
    r = await client.post(f"{BASE}/conflictos/{c.id}/resolver", json={"accion": "restaurar_en_google"},
                          headers=bearer(token_recepcion))
    assert r.status_code == 200
    await ciclo(session_factory, proveedor_gcal)
    vinculos = await eventos(session_factory, conexion)
    assert [(v.generacion, v.estado) for v in vinculos] == [(0, "borrado"), (1, "sincronizado")]
    assert len(proveedor_gcal.vigentes()) == 1 and proveedor_gcal.vigentes()[0].inicio == MANANA


async def test_desvincular_deja_el_evento_en_google_y_ningun_ciclo_lo_toca(
        client: AsyncClient, session_factory: Factory, proveedor_gcal: ProveedorFalso, token_recepcion: str) -> None:
    _, conexion, turno, _, c = await _movido(session_factory, proveedor_gcal)
    r = await client.post(f"{BASE}/conflictos/{c.id}/resolver", json={"accion": "desvincular"},
                          headers=bearer(token_recepcion))
    assert r.status_code == 200
    await poner_turno(session_factory, turno, estado="cancelado")
    antes = len(proveedor_gcal.llamadas)
    await ciclo(session_factory, proveedor_gcal)
    assert [m for m in proveedor_gcal.llamadas[antes:] if m in ("insertar", "actualizar", "borrar")] == []
    assert [e.estado for e in await eventos(session_factory, conexion) if e.origen == "sistema"] == ["desvinculado"]
    assert len(proveedor_gcal.vigentes()) == 1


async def test_revisado_cierra_el_solape_y_uno_nuevo_aparece_si_la_franja_se_mueve_a_otra_superposicion(
        client: AsyncClient, session_factory: Factory, proveedor_gcal: ProveedorFalso, token_recepcion: str) -> None:
    mundo = await sembrar_mundo(session_factory)
    await sembrar_conexion(session_factory, mundo["ana"])
    await insertar_turno(session_factory, mundo, MANANA)
    franja = proveedor_gcal.crear_ocupado(MANANA, MANANA + timedelta(hours=1))
    await ciclo(session_factory, proveedor_gcal)
    [c] = await conflictos(session_factory)
    r = await client.post(f"{BASE}/conflictos/{c.id}/resolver", json={"accion": "revisado"},
                          headers=bearer(token_recepcion))
    assert r.status_code == 200
    await ciclo(session_factory, proveedor_gcal)
    assert len(await conflictos(session_factory)) == 1  # mismo desacuerdo revisado: no vuelve a abrirse
    proveedor_gcal.mover(franja, MANANA + timedelta(minutes=15), MANANA + timedelta(hours=1, minutes=15))
    await ciclo(session_factory, proveedor_gcal)
    assert [x.estado for x in await conflictos(session_factory)] == ["resuelto", "abierto"]


async def test_acciones_invalidas_roles_sin_permiso_y_conflictos_cerrados(
        client: AsyncClient, session_factory: Factory, proveedor_gcal: ProveedorFalso, token_recepcion: str) -> None:
    mundo = await sembrar_mundo(session_factory)
    await sembrar_conexion(session_factory, mundo["ana"])
    turno = await insertar_turno(session_factory, mundo, MANANA)
    proveedor_gcal.crear_ocupado(MANANA, MANANA + timedelta(hours=1))
    await ciclo(session_factory, proveedor_gcal)
    [c] = await conflictos(session_factory)
    _, token_odonto = await crear_usuario_panel(session_factory, "ana.odonto@example.com", ["odontologo"],
                                                profesional_id=mundo["ana"])
    url = f"{BASE}/conflictos/{c.id}/resolver"
    r = await client.post(url, json={"accion": "restaurar_en_google"}, headers=bearer(token_recepcion))
    assert (r.status_code, r.json()["motivo"]) == (422, "accion_no_valida")
    assert (await client.post(url, json={"accion": "revisado"}, headers=bearer(token_odonto))).status_code == 403
    assert (await client.post(url, json={"accion": "revisado"})).status_code == 401
    assert (await client.post(f"{BASE}/conflictos/999999/resolver", json={"accion": "revisado"},
                              headers=bearer(token_recepcion))).status_code == 404
    assert (await conflictos(session_factory))[0].estado == "abierto"
    await poner_turno(session_factory, turno, estado="cancelado")  # se canceló entre medio
    r = await client.post(url, json={"accion": "revisado"}, headers=bearer(token_recepcion))
    assert (r.status_code, r.json()["motivo"]) == (409, "conflicto_cerrado")
    assert (await conflictos(session_factory))[0].resolucion == "turno_cancelado"
    r = await client.post(url, json={"accion": "revisado"}, headers=bearer(token_recepcion))
    assert r.status_code == 409
