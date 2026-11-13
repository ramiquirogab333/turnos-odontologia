"""C-08 (1.4, 6.1, 6.3): cambios de estado del panel. PostgreSQL real. Datos 100 % sintéticos (R19)."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.models.core import RegistroAuditoria
from app.pagos.errores import MarcadoNoHabilitadoError, OperacionReintentableError
from app.pagos.estados import TransicionInvalidaError, ausente_habilitado_desde
from app.pagos.service import cambiar_estado_turno
from app.turnos.models import Turno
from tests.conftest import bearer, crear_sesion_sintetica, crear_usuario_panel
from tests.panel_helpers import LUNES, insertar_pago, insertar_turno, local, pagos, sembrar_mundo, turno

INICIO = datetime(2031, 7, 7, 13, 0, tzinfo=timezone.utc)
TOLERANCIA = timedelta(minutes=10)


def _habilitado(inicio: datetime) -> datetime:
    return ausente_habilitado_desde(inicio, TOLERANCIA)


async def _turno(factory, ids, estado="reservado", inicio=INICIO) -> int:
    async with factory() as s:
        t = Turno(profesional_id=ids["profesional_id"], sillon_id=ids["sillon_id"],
                  tratamiento_id=ids["tratamiento_id"], inicio=inicio, fin=inicio + timedelta(minutes=30),
                  estado=estado, en_espera_vence_en=inicio if estado == "en_espera" else None)
        s.add(t)
        await s.flush()
        await s.commit()
        return int(t.id)


async def _estado(factory, turno_id) -> str:
    async with factory() as s:
        return (await s.execute(select(Turno.estado).where(Turno.id == turno_id))).scalar_one()


async def _auditorias(factory, turno_id) -> int:
    async with factory() as s:
        return (await s.execute(select(func.count()).select_from(RegistroAuditoria).where(
            RegistroAuditoria.entidad == "turno", RegistroAuditoria.entidad_id == str(turno_id)))).scalar_one()


async def test_antes_del_instante_habilitado_lanza_error_y_no_cambia_nada(session_factory, seed_ids) -> None:
    turno_id = await _turno(session_factory, seed_ids)
    ahora = INICIO + timedelta(minutes=9, seconds=59)
    async with session_factory() as s:
        with pytest.raises(MarcadoNoHabilitadoError) as exc:
            await cambiar_estado_turno(s, turno_id, "ausente", 1, ahora=ahora, habilitado_desde=_habilitado)
    assert exc.value.habilitado_desde == INICIO + TOLERANCIA
    assert await _estado(session_factory, turno_id) == "reservado"
    assert await _auditorias(session_factory, turno_id) == 0


async def test_exactamente_en_el_instante_habilitado_acepta(session_factory, seed_ids) -> None:
    turno_id = await _turno(session_factory, seed_ids)
    async with session_factory() as s:
        r = await cambiar_estado_turno(s, turno_id, "ausente", None, ahora=INICIO + TOLERANCIA,
                                       habilitado_desde=_habilitado)
    assert r.estado_turno == "ausente"
    assert await _estado(session_factory, turno_id) == "ausente"


async def test_el_instante_se_calcula_con_el_inicio_real_del_turno_bajo_lock(session_factory, seed_ids) -> None:
    visto: list[datetime] = []

    def espia(inicio: datetime) -> datetime:
        visto.append(inicio)
        return inicio

    turno_id = await _turno(session_factory, seed_ids)
    async with session_factory() as s:
        await cambiar_estado_turno(s, turno_id, "ausente", None, ahora=INICIO, habilitado_desde=espia)
    assert visto == [INICIO]


async def test_un_estado_invalido_gana_sobre_el_momento(session_factory, seed_ids) -> None:
    turno_id = await _turno(session_factory, seed_ids, estado="atendido")
    async with session_factory() as s:
        with pytest.raises(TransicionInvalidaError):
            await cambiar_estado_turno(s, turno_id, "ausente", None, ahora=INICIO - timedelta(days=1),
                                       habilitado_desde=_habilitado)


async def test_sin_el_parametro_el_comportamiento_es_el_de_siempre(session_factory, seed_ids) -> None:
    turno_id = await _turno(session_factory, seed_ids)
    async with session_factory() as s:
        r = await cambiar_estado_turno(s, turno_id, "ausente", None, ahora=INICIO - timedelta(days=30))
    assert r.estado_turno == "ausente"


# ===========================================================================
# 6.1 / 6.3 Endpoints del panel: ausente, atendido y cancelar
# ===========================================================================

MARTES = LUNES + timedelta(days=1)
INICIO_PANEL = local(MARTES, "09:00")


@pytest.fixture
async def mundo(session_factory, clean_db):
    return await sembrar_mundo(session_factory)


@pytest.fixture
async def rec(session_factory, mundo):
    usuario_id, token = await crear_usuario_panel(session_factory, "recepcion@turnos.test", ["recepcion"])
    return {"id": usuario_id, "cab": bearer(token)}


async def _audit_origen(factory, turno_id: int, origen: str) -> list[RegistroAuditoria]:
    async with factory() as s:
        filas = (await s.execute(select(RegistroAuditoria).where(
            RegistroAuditoria.entidad == "turno", RegistroAuditoria.entidad_id == str(turno_id)))).scalars().all()
    return [f for f in filas if (f.datos_despues or {}).get("origen") == origen]


async def _total_auditorias(factory) -> int:
    async with factory() as s:
        return (await s.execute(select(func.count()).select_from(RegistroAuditoria))).scalar_one()


async def _post(client, rec, turno_id: int, accion: str):
    return await client.post(f"/api/panel/turnos/{turno_id}/{accion}", headers=rec["cab"])


# --- ausente ----------------------------------------------------------------------------------------------

async def test_ausente_con_sena_acreditada_a_los_15_minutos_queda_no_reembolsado(
        client, rec, mundo, session_factory, reloj, notificador) -> None:
    tid = await insertar_turno(session_factory, mundo, INICIO_PANEL, estado="confirmado")
    await insertar_pago(session_factory, tid, "acreditado", monto="3000.00")
    reloj(INICIO_PANEL + timedelta(minutes=15))
    r = await _post(client, rec, tid, "ausente")
    assert r.status_code == 200, r.text
    assert r.json() == {"turno_id": tid, "estado": "ausente", "estado_sena": "no_reembolsado"}  # R9
    (pago,) = await pagos(session_factory, tid)
    assert pago.estado == "no_reembolsado" and pago.monto == 3000
    assert (await turno(session_factory, tid)).estado == "ausente"
    (registro,) = await _audit_origen(session_factory, tid, "marcado_ausente_panel")
    assert registro.usuario_id == rec["id"] and registro.datos_antes == {"estado": "confirmado"}
    assert notificador.eventos == []  # O15: ausente no publica


async def test_ausente_a_los_9_59_es_409_marcado_no_habilitado_con_el_instante_y_no_cambia_nada(
        client, rec, mundo, session_factory, reloj) -> None:
    tid = await insertar_turno(session_factory, mundo, INICIO_PANEL)
    await insertar_pago(session_factory, tid, "acreditado")
    reloj(INICIO_PANEL + timedelta(minutes=9, seconds=59))
    antes = await _total_auditorias(session_factory)
    r = await _post(client, rec, tid, "ausente")
    assert r.status_code == 409, r.text
    assert r.json()["motivo"] == "marcado_no_habilitado"
    assert r.json()["habilitado_desde"] == "2031-11-18T09:10:00-03:00"
    assert (await turno(session_factory, tid)).estado == "reservado"
    assert (await pagos(session_factory, tid))[0].estado == "acreditado"
    assert await _total_auditorias(session_factory) == antes


async def test_ausente_exactamente_a_los_10_minutos_sin_sena_se_acepta_y_no_crea_pago(
        client, rec, mundo, session_factory, reloj) -> None:
    tid = await insertar_turno(session_factory, mundo, INICIO_PANEL, origen="manual", con_codigo=False)
    reloj(INICIO_PANEL + timedelta(minutes=10))
    r = await _post(client, rec, tid, "ausente")
    assert r.status_code == 200 and r.json()["estado_sena"] is None
    assert await pagos(session_factory, tid) == []


@pytest.mark.parametrize("estado", ["en_espera", "ausente", "atendido", "cancelado"])
async def test_ausente_desde_un_estado_invalido_es_409_transicion_invalida(
        client, rec, mundo, session_factory, reloj, estado) -> None:
    tid = await insertar_turno(session_factory, mundo, INICIO_PANEL, estado=estado)
    reloj(INICIO_PANEL + timedelta(hours=1))
    r = await _post(client, rec, tid, "ausente")
    assert r.status_code == 409 and r.json()["motivo"] == "transicion_invalida"
    assert (await turno(session_factory, tid)).estado == estado


@pytest.mark.parametrize("env,minutos_despues,esperado", [("0", 0, 200), ("25", 15, 409), ("25", 25, 200)])
async def test_la_tolerancia_configurable_se_aplica_al_endpoint(
        client, rec, mundo, session_factory, reloj, monkeypatch, env, minutos_despues, esperado) -> None:
    monkeypatch.setenv("AUSENTE_TOLERANCIA_MINUTOS", env)
    tid = await insertar_turno(session_factory, mundo, INICIO_PANEL)
    reloj(INICIO_PANEL + timedelta(minutes=minutos_despues))
    assert (await _post(client, rec, tid, "ausente")).status_code == esperado


# --- atendido ---------------------------------------------------------------------------------------------

async def test_atendido_el_mismo_dia_antes_de_la_hora_acepta_conserva_la_sena_y_sigue_ocupando(
        client, rec, mundo, session_factory, reloj, notificador) -> None:
    inicio = local(MARTES, "11:00")
    tid = await insertar_turno(session_factory, mundo, inicio)
    await insertar_pago(session_factory, tid, "acreditado")
    reloj(local(MARTES, "09:30"))
    r = await _post(client, rec, tid, "atendido")
    assert r.status_code == 200, r.text
    assert r.json() == {"turno_id": tid, "estado": "atendido", "estado_sena": None}
    assert (await pagos(session_factory, tid))[0].estado == "acreditado"
    disp = await client.get("/api/public/disponibilidad", params={
        "profesional_id": mundo["ana"], "tratamiento_id": mundo["trat"],
        "desde": MARTES.isoformat(), "hasta": MARTES.isoformat()})
    horarios = [datetime.fromisoformat(s["inicio"]) for s in disp.json()["slots"]]
    assert inicio not in horarios and local(MARTES, "10:30") in horarios  # O19
    assert len(await _audit_origen(session_factory, tid, "marcado_atendido_panel")) == 1
    assert notificador.eventos == []


async def test_atendido_a_las_23_59_59_del_dia_anterior_es_409_y_a_las_00_00_local_se_acepta(
        client, rec, mundo, session_factory, reloj) -> None:
    tid = await insertar_turno(session_factory, mundo, INICIO_PANEL)
    reloj(local(LUNES, "23:59") + timedelta(seconds=59))
    r = await _post(client, rec, tid, "atendido")
    assert r.status_code == 409 and r.json()["motivo"] == "marcado_no_habilitado"
    assert r.json()["habilitado_desde"] == "2031-11-18T00:00:00-03:00"
    assert (await turno(session_factory, tid)).estado == "reservado"
    reloj(local(MARTES, "00:00"))  # en UTC son las 03:00
    assert (await _post(client, rec, tid, "atendido")).status_code == 200


@pytest.mark.parametrize("estado", ["ausente", "cancelado", "en_espera"])
async def test_atendido_desde_un_estado_invalido_es_409(client, rec, mundo, session_factory, reloj, estado) -> None:
    tid = await insertar_turno(session_factory, mundo, INICIO_PANEL, estado=estado)
    reloj(INICIO_PANEL)
    r = await _post(client, rec, tid, "atendido")
    assert r.status_code == 409 and r.json()["motivo"] == "transicion_invalida"


async def test_turno_inexistente_es_404_y_el_doble_marcado_no_duplica_la_auditoria(
        client, rec, mundo, session_factory, reloj) -> None:
    reloj(INICIO_PANEL)
    for accion in ("atendido", "ausente", "cancelar"):
        assert (await _post(client, rec, 999999, accion)).status_code == 404
    tid = await insertar_turno(session_factory, mundo, INICIO_PANEL)
    assert (await _post(client, rec, tid, "atendido")).status_code == 200
    segundo = await _post(client, rec, tid, "atendido")
    assert segundo.status_code == 409 and segundo.json()["motivo"] == "transicion_invalida"
    assert len(await _audit_origen(session_factory, tid, "marcado_atendido_panel")) == 1


# --- permisos y errores transitorios ------------------------------------------------------------------------

@pytest.fixture
async def dra(session_factory, mundo):
    """La Dra. Ana Ficticia: rol odontologo asociada a la profesional ``ana`` del mundo de prueba (C-11, O15)."""
    usuario_id, token = await crear_usuario_panel(session_factory, "dra.ficticia@turnos.test", ["odontologo"],
                                                  profesional_id=mundo["ana"])
    return {"id": usuario_id, "cab": bearer(token)}


async def test_sin_token_o_con_refresh_es_401_y_no_cambia_nada(client, mundo, session_factory, reloj) -> None:
    tid = await insertar_turno(session_factory, mundo, INICIO_PANEL)
    reloj(INICIO_PANEL + timedelta(hours=1))
    uid, _ = await crear_usuario_panel(session_factory, "x@turnos.test", ["odontologo"], profesional_id=mundo["ana"])
    _, _, refresh = await crear_sesion_sintetica(session_factory, uid, "x@turnos.test", ["odontologo"])
    for accion in ("ausente", "atendido", "cancelar"):
        assert (await client.post(f"/api/panel/turnos/{tid}/{accion}")).status_code == 401
        assert (await client.post(f"/api/panel/turnos/{tid}/{accion}", headers=bearer(refresh))).status_code == 401
    assert (await turno(session_factory, tid)).estado == "reservado"


async def test_la_odontologa_marca_atendido_su_propio_turno_y_la_sena_no_cambia(
        client, dra, mundo, session_factory, reloj) -> None:
    inicio = local(MARTES, "11:00")
    tid = await insertar_turno(session_factory, mundo, inicio, estado="confirmado")
    await insertar_pago(session_factory, tid, "acreditado", monto="3000.00")
    reloj(local(MARTES, "10:45"))
    r = await _post(client, dra, tid, "atendido")
    assert r.status_code == 200, r.text
    assert r.json() == {"turno_id": tid, "estado": "atendido", "estado_sena": None}  # mismo contrato que recepción
    assert (await turno(session_factory, tid)).estado == "atendido"
    assert (await pagos(session_factory, tid))[0].estado == "acreditado"
    (registro,) = await _audit_origen(session_factory, tid, "marcado_atendido_panel")
    assert registro.usuario_id == dra["id"]
    volcado = str(registro.datos_antes) + str(registro.datos_despues)
    assert "Carlos" not in volcado and "+549" not in volcado


async def test_turno_de_otra_profesional_ya_ausente_o_inexistente_son_403_turno_ajeno_con_el_mismo_cuerpo(
        client, dra, mundo, session_factory, reloj) -> None:
    ajeno = await insertar_turno(session_factory, mundo, local(MARTES, "10:00"), prof="bruno", sillon="s2")
    ajeno_ausente = await insertar_turno(session_factory, mundo, local(MARTES, "09:00"), prof="bruno", sillon="s2",
                                         estado="ausente")
    reloj(local(MARTES, "10:45"))
    antes = await _total_auditorias(session_factory)
    respuestas = [await _post(client, dra, tid, "atendido") for tid in (ajeno, ajeno_ausente, 987654)]
    assert [r.status_code for r in respuestas] == [403, 403, 403]
    assert respuestas[0].json() == respuestas[1].json() == respuestas[2].json()  # no revela existencia ni estado
    assert respuestas[0].json()["motivo"] == "turno_ajeno"
    assert (await turno(session_factory, ajeno)).estado == "reservado"
    assert (await turno(session_factory, ajeno_ausente)).estado == "ausente"
    assert await _total_auditorias(session_factory) == antes


@pytest.mark.parametrize("accion", ["ausente", "cancelar"])
async def test_la_odontologa_no_marca_ausente_ni_cancela_su_turno(client, dra, mundo, session_factory, reloj, accion) -> None:
    tid = await insertar_turno(session_factory, mundo, INICIO_PANEL)
    reloj(INICIO_PANEL + timedelta(hours=1))
    assert (await _post(client, dra, tid, accion)).status_code == 403
    assert (await turno(session_factory, tid)).estado == "reservado"


async def test_la_odontologa_no_da_altas_manuales(client, dra, mundo, session_factory, reloj) -> None:
    reloj(local(LUNES, "07:00"))
    r = await client.post("/api/panel/turnos", headers=dra["cab"], json={
        "profesional_id": mundo["ana"], "tratamiento_id": mundo["trat"], "inicio": local(MARTES, "10:00").isoformat(),
        "nombre": "Carlos Sintético", "telefono": "+5491144445555"})
    assert r.status_code == 403


async def test_odontologa_sin_profesional_asociado_es_403_sin_profesional_asociado(
        client, mundo, session_factory, reloj) -> None:
    tid = await insertar_turno(session_factory, mundo, INICIO_PANEL)
    reloj(INICIO_PANEL + timedelta(hours=1))
    _, token = await crear_usuario_panel(session_factory, "sinprof@turnos.test", ["odontologo"])
    r = await client.post(f"/api/panel/turnos/{tid}/atendido", headers=bearer(token))
    assert (r.status_code, r.json()["motivo"]) == (403, "sin_profesional_asociado")


async def test_usuario_sin_roles_del_panel_es_403_sin_acceso_al_panel(client, mundo, session_factory, reloj) -> None:
    tid = await insertar_turno(session_factory, mundo, INICIO_PANEL)
    reloj(INICIO_PANEL + timedelta(hours=1))
    _, token = await crear_usuario_panel(session_factory, "sinroles@turnos.test", [])
    r = await client.post(f"/api/panel/turnos/{tid}/atendido", headers=bearer(token))
    assert (r.status_code, r.json()["motivo"]) == (403, "sin_acceso_al_panel")


async def test_usuario_odontologo_y_recepcion_marca_el_turno_de_otra_profesional(
        client, mundo, session_factory, reloj) -> None:
    ajeno = await insertar_turno(session_factory, mundo, INICIO_PANEL, prof="bruno", sillon="s2")
    reloj(INICIO_PANEL + timedelta(hours=1))
    _, token = await crear_usuario_panel(session_factory, "multi@turnos.test", ["odontologo", "recepcion"],
                                         profesional_id=mundo["ana"])
    assert (await client.post(f"/api/panel/turnos/{ajeno}/atendido", headers=bearer(token))).status_code == 200
    assert (await turno(session_factory, ajeno)).estado == "atendido"


# --- 9.4 RN-TU-12 sobre los turnos propios de la odontóloga ---------------------------------------------------

async def test_un_segundo_antes_de_las_cero_horas_409_y_a_las_cero_horas_200(client, dra, mundo, session_factory, reloj) -> None:
    tid = await insertar_turno(session_factory, mundo, INICIO_PANEL)
    reloj(local(LUNES, "23:59:59"))
    antes = await _post(client, dra, tid, "atendido")
    assert (antes.status_code, antes.json()["motivo"]) == (409, "marcado_no_habilitado")
    assert datetime.fromisoformat(antes.json()["habilitado_desde"]) == local(MARTES, "00:00")
    assert (await turno(session_factory, tid)).estado == "reservado"
    reloj(local(MARTES, "00:00"))
    assert (await _post(client, dra, tid, "atendido")).status_code == 200


@pytest.mark.parametrize("estado", ["atendido", "ausente", "cancelado", "en_espera"])
async def test_estados_que_no_admiten_atendido_son_409_transicion_invalida(
        client, dra, mundo, session_factory, reloj, estado) -> None:
    tid = await insertar_turno(session_factory, mundo, INICIO_PANEL, estado=estado,
                               vence=INICIO_PANEL + timedelta(hours=2))
    reloj(INICIO_PANEL + timedelta(hours=1))
    r = await _post(client, dra, tid, "atendido")
    assert (r.status_code, r.json()["motivo"]) == (409, "transicion_invalida")
    assert (await turno(session_factory, tid)).estado == estado


async def test_turno_ajeno_atendido_es_403_y_nunca_409(client, dra, mundo, session_factory, reloj) -> None:
    tid = await insertar_turno(session_factory, mundo, INICIO_PANEL, prof="bruno", sillon="s2", estado="atendido")
    reloj(INICIO_PANEL + timedelta(hours=1))
    r = await _post(client, dra, tid, "atendido")
    assert (r.status_code, r.json()["motivo"]) == (403, "turno_ajeno")


async def test_recepcion_y_la_odontologa_marcan_a_la_vez_un_200_un_409_y_una_sola_auditoria(
        client, rec, dra, mundo, session_factory, reloj) -> None:
    tid = await insertar_turno(session_factory, mundo, INICIO_PANEL)
    reloj(INICIO_PANEL + timedelta(hours=1))
    r1, r2 = await asyncio.gather(_post(client, rec, tid, "atendido"), _post(client, dra, tid, "atendido"))
    assert sorted([r1.status_code, r2.status_code]) == [200, 409], (r1.text, r2.text)
    perdedora = r1 if r1.status_code == 409 else r2
    assert perdedora.json()["motivo"] == "transicion_invalida"
    assert len(await _audit_origen(session_factory, tid, "marcado_atendido_panel")) == 1


@pytest.mark.parametrize("accion", ["ausente", "atendido", "cancelar"])
async def test_reintentos_agotados_son_503(client, rec, mundo, session_factory, reloj, monkeypatch, accion) -> None:
    tid = await insertar_turno(session_factory, mundo, INICIO_PANEL)
    reloj(INICIO_PANEL + timedelta(hours=1))

    async def agotado(*_a, **_k):
        raise OperacionReintentableError()

    monkeypatch.setattr("app.panel.service.cambiar_estado_turno", agotado)
    assert (await _post(client, rec, tid, accion)).status_code == 503


# --- 6.3 cancelar -----------------------------------------------------------------------------------------

async def test_cancelar_a_48_horas_devuelve_la_sena_libera_el_horario_y_publica_el_evento(
        client, rec, mundo, session_factory, reloj, notificador) -> None:
    tid = await insertar_turno(session_factory, mundo, INICIO_PANEL)
    await insertar_pago(session_factory, tid, "acreditado")
    reloj(INICIO_PANEL - timedelta(hours=48))
    r = await _post(client, rec, tid, "cancelar")
    assert r.status_code == 200, r.text
    assert r.json() == {"turno_id": tid, "estado": "cancelado", "estado_sena": "a_reembolsar"}
    assert (await pagos(session_factory, tid))[0].estado == "a_reembolsar"
    disp = await client.get("/api/public/disponibilidad", params={
        "profesional_id": mundo["ana"], "tratamiento_id": mundo["trat"],
        "desde": MARTES.isoformat(), "hasta": MARTES.isoformat()})
    assert INICIO_PANEL in [datetime.fromisoformat(s["inicio"]) for s in disp.json()["slots"]]
    (registro,) = await _audit_origen(session_factory, tid, "cancelacion_panel")
    assert registro.usuario_id == rec["id"]
    (evento,) = notificador.eventos
    assert (evento.tipo, evento.turno_id, evento.profesional_id) == ("turno_cancelado", tid, mundo["ana"])
    assert (evento.inicio_anterior, evento.inicio_nuevo) == (INICIO_PANEL, None)


async def test_cancelar_a_23h59_es_409_fuera_de_plazo_con_el_limite_y_no_cambia_ni_publica(
        client, rec, mundo, session_factory, reloj, notificador) -> None:
    tid = await insertar_turno(session_factory, mundo, INICIO_PANEL, estado="confirmado")
    await insertar_pago(session_factory, tid, "acreditado")
    reloj(INICIO_PANEL - timedelta(hours=23, minutes=59))
    antes = await _total_auditorias(session_factory)
    r = await _post(client, rec, tid, "cancelar")
    assert r.status_code == 409 and r.json()["motivo"] == "fuera_de_plazo"
    assert r.json()["limite_cambios"] == "2031-11-17T09:00:00-03:00"
    assert (await turno(session_factory, tid)).estado == "confirmado"
    assert (await pagos(session_factory, tid))[0].estado == "acreditado"
    assert notificador.eventos == [] and await _total_auditorias(session_factory) == antes


async def test_cancelar_exactamente_a_24_horas_se_acepta(client, rec, mundo, session_factory, reloj) -> None:
    tid = await insertar_turno(session_factory, mundo, INICIO_PANEL)
    await insertar_pago(session_factory, tid, "acreditado")
    reloj(INICIO_PANEL - timedelta(hours=24))
    r = await _post(client, rec, tid, "cancelar")
    assert r.status_code == 200 and r.json()["estado_sena"] == "a_reembolsar"


async def test_cancelar_una_pre_reserva_en_cualquier_momento_la_deja_vencida_sin_evento(
        client, rec, mundo, session_factory, reloj, notificador) -> None:
    tid = await insertar_turno(session_factory, mundo, INICIO_PANEL, estado="en_espera",
                               vence=INICIO_PANEL + timedelta(hours=1))
    await insertar_pago(session_factory, tid, "pendiente", medio="mercadopago")
    reloj(INICIO_PANEL - timedelta(hours=1))  # a menos de 24 h: para una pre-reserva no hay ventana (O12)
    r = await _post(client, rec, tid, "cancelar")
    assert r.status_code == 200 and r.json() == {"turno_id": tid, "estado": "cancelado", "estado_sena": "vencido"}
    assert notificador.eventos == []


@pytest.mark.parametrize("estado", ["ausente", "atendido", "cancelado"])
async def test_cancelar_un_turno_en_estado_final_es_409(client, rec, mundo, session_factory, reloj, estado) -> None:
    tid = await insertar_turno(session_factory, mundo, INICIO_PANEL, estado=estado)
    reloj(INICIO_PANEL - timedelta(days=5))
    r = await _post(client, rec, tid, "cancelar")
    assert r.status_code == 409 and r.json()["motivo"] == "transicion_invalida"


async def test_un_publicador_caido_no_revierte_la_cancelacion(
        client, rec, mundo, session_factory, reloj, notificador) -> None:
    notificador.falla = True
    tid = await insertar_turno(session_factory, mundo, INICIO_PANEL)
    reloj(INICIO_PANEL - timedelta(hours=48))
    r = await _post(client, rec, tid, "cancelar")
    assert r.status_code == 200
    assert (await turno(session_factory, tid)).estado == "cancelado"
