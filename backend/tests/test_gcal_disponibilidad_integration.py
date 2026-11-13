"""C-10 (10.1-10.4): las franjas ocupadas de Google en la disponibilidad pública, la reprogramación, el alta manual y la
agenda del panel. PostgreSQL real, sin red. Datos sintéticos (R19)."""

from datetime import timedelta

import pytest

from tests.conftest import bearer, crear_usuario_panel
from tests.gcal_helpers import AHORA, ciclo, sembrar_conexion, sembrar_franja
from tests.panel_helpers import (LUNES, cuerpo_alta, insertar_turno, local, sembrar_mundo)
from tests.sena_helpers import cabecera, local as local_sena, TELEFONO
from tests.test_sena_transiciones_integration import _reservado_con_sena

MARTES = LUNES + timedelta(days=1)
DISPONIBILIDAD = "/api/public/disponibilidad"


@pytest.fixture
async def mundo(session_factory, clean_db):
    return await sembrar_mundo(session_factory)


async def _horas(client, mundo, dia, profesional: str = "ana") -> list[str]:
    r = await client.get(DISPONIBILIDAD, params={"profesional_id": mundo[profesional], "tratamiento_id": mundo["trat"],
                                                 "desde": dia.isoformat(), "hasta": dia.isoformat()})
    assert r.status_code == 200, r.text
    return [s["inicio"][11:16] for s in r.json()["slots"]]


# --- 10.1 Reserva pública -----------------------------------------------------------------------------------------

async def test_la_franja_ocupada_en_google_no_se_ofrece_y_los_bordes_si(client, mundo, session_factory) -> None:
    conexion = await sembrar_conexion(session_factory, mundo["ana"])
    await sembrar_franja(session_factory, conexion, local(MARTES, "11:00"), local(MARTES, "12:00"))
    horas = await _horas(client, mundo, MARTES)
    assert "11:00" not in horas and "11:30" not in horas
    assert "10:30" in horas and "12:00" in horas  # los bordes semiabiertos [11:00, 12:00)


async def test_la_franja_de_una_profesional_no_afecta_a_la_otra(client, mundo, session_factory) -> None:
    conexion = await sembrar_conexion(session_factory, mundo["ana"])
    await sembrar_franja(session_factory, conexion, local(MARTES, "11:00"), local(MARTES, "12:00"))
    assert "11:00" in await _horas(client, mundo, MARTES, "bruno")


@pytest.mark.parametrize("estado,excluye", [("activa", True), ("revocada", True), ("desconectada", False),
                                            ("pendiente", False)])
async def test_segun_el_estado_de_la_conexion_las_franjas_conocidas_siguen_o_dejan_de_excluirse(
        client, mundo, session_factory, estado: str, excluye: bool) -> None:
    from datetime import datetime, timezone

    campos = {"oauth_nonce_hash": "h", "oauth_expira_en": datetime(2031, 1, 1, tzinfo=timezone.utc)} \
        if estado == "pendiente" else {}
    conexion = await sembrar_conexion(session_factory, mundo["ana"], estado=estado, **campos)
    await sembrar_franja(session_factory, conexion, local(MARTES, "11:00"), local(MARTES, "12:00"))
    assert ("11:00" not in await _horas(client, mundo, MARTES)) is excluye


async def test_una_franja_que_no_ocupa_no_excluye(client, mundo, session_factory) -> None:
    conexion = await sembrar_conexion(session_factory, mundo["ana"])
    await sembrar_franja(session_factory, conexion, local(MARTES, "11:00"), local(MARTES, "12:00"), ocupa=False)
    assert "11:00" in await _horas(client, mundo, MARTES)


async def test_reservar_sobre_la_franja_da_409_profesional_con_alternativas_y_sin_crear_turno(
        client, mundo, session_factory) -> None:
    from sqlalchemy import func, select

    from app.turnos.models import Turno

    conexion = await sembrar_conexion(session_factory, mundo["ana"])
    await sembrar_franja(session_factory, conexion, local(MARTES, "11:00"), local(MARTES, "12:00"))
    r = await client.post("/api/public/turnos", json={
        "nombre": "Carlos Sintético", "telefono": TELEFONO, "tratamiento_id": mundo["trat"],
        "profesional_id": mundo["ana"], "inicio": local(MARTES, "11:00").isoformat()})
    assert r.status_code == 409 and r.json()["motivo"] == "profesional" and r.json()["alternativas"]
    assert "google" not in r.text.lower()  # no se revela el motivo
    async with session_factory() as s:
        assert (await s.execute(select(func.count()).select_from(Turno))).scalar_one() == 0


# --- 10.1 Reprogramación del paciente ------------------------------------------------------------------------------

async def _reprogramar(client, reserva, inicio, hhmm: str):
    return await client.post("/api/public/gestion/reprogramar", json={"inicio": local_sena(inicio.date(), hhmm).isoformat()},
                             headers=cabecera(reserva))


async def test_reprogramar_a_un_horario_libre_o_que_empieza_cuando_termina_la_franja_se_acepta(
        client, seed_ids, session_factory, pasarela, reloj) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    conexion = await sembrar_conexion(session_factory, seed_ids["profesional_id"])
    await sembrar_franja(session_factory, conexion, local_sena(inicio.date(), "15:00"),
                         local_sena(inicio.date(), "16:00"))
    reloj(inicio - timedelta(days=5))
    r = await _reprogramar(client, reserva, inicio, "16:00")  # borde: la franja es [15:00, 16:00)
    assert r.status_code == 200, r.text


async def test_reprogramar_sobre_la_franja_ocupada_da_409_con_alternativas_y_no_cambia_el_turno(
        client, seed_ids, session_factory, pasarela, reloj) -> None:
    from tests.sena_helpers import turno_de

    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    conexion = await sembrar_conexion(session_factory, seed_ids["profesional_id"])
    await sembrar_franja(session_factory, conexion, local_sena(inicio.date(), "15:00"),
                         local_sena(inicio.date(), "16:00"))
    reloj(inicio - timedelta(days=5))
    r = await _reprogramar(client, reserva, inicio, "15:30")
    assert r.status_code == 409 and r.json()["motivo"] == "profesional"
    horas = [a["inicio"][11:16] for a in r.json()["alternativas"]]
    assert "15:00" not in horas and "15:30" not in horas
    assert (await turno_de(session_factory, reserva["turno_id"])).inicio == inicio


# --- 10.3 Alta manual ---------------------------------------------------------------------------------------------

@pytest.fixture
async def rec(session_factory, mundo, reloj):
    reloj(local(LUNES, "07:00"))
    return bearer((await crear_usuario_panel(session_factory, "recepcion@turnos.test", ["recepcion"]))[1])


async def test_alta_manual_sobre_horario_libre_en_google_avisa_false(client, mundo, session_factory, rec) -> None:
    await sembrar_conexion(session_factory, mundo["ana"])
    r = await client.post("/api/panel/turnos", json=cuerpo_alta(mundo, local(MARTES, "11:00")), headers=rec)
    assert r.status_code == 201 and r.json()["aviso_google_calendar"] is False


async def test_alta_manual_sobre_una_franja_ocupada_se_acepta_con_aviso_y_queda_en_conflicto_tras_el_ciclo(
        client, mundo, session_factory, rec, proveedor_gcal) -> None:
    from tests.gcal_helpers import conflictos

    await sembrar_conexion(session_factory, mundo["ana"])
    proveedor_gcal.crear_ocupado(local(MARTES, "11:00"), local(MARTES, "12:00"))
    await ciclo(session_factory, proveedor_gcal, ahora=local(LUNES, "07:00"))  # la franja llega por el pull
    r = await client.post("/api/panel/turnos", json=cuerpo_alta(mundo, local(MARTES, "11:00")), headers=rec)
    assert r.status_code == 201 and r.json()["aviso_google_calendar"] is True
    await ciclo(session_factory, proveedor_gcal, ahora=local(LUNES, "07:00"))
    assert [c.tipo for c in await conflictos(session_factory, "abierto")] == ["solapa_evento_externo"]


async def test_alta_manual_de_una_profesional_sin_conexion_avisa_false(client, mundo, session_factory, rec) -> None:
    r = await client.post("/api/panel/turnos", json=cuerpo_alta(mundo, local(MARTES, "11:00"), profesional_id=mundo["bruno"]),
                          headers=rec)
    assert r.status_code == 201 and r.json()["aviso_google_calendar"] is False


# --- 10.4 Agenda ---------------------------------------------------------------------------------------------------

async def _agenda(client, cab, dia, **params):
    return await client.get("/api/panel/agenda", params={"vista": "dia", "fecha": dia.isoformat(), **params}, headers=cab)


async def test_la_agenda_trae_las_franjas_con_alcance_por_rol_y_sin_titulo(client, mundo, session_factory, rec) -> None:
    conexion = await sembrar_conexion(session_factory, mundo["ana"])
    await sembrar_franja(session_factory, conexion, local(MARTES, "15:00"), local(MARTES, "16:00"))
    j = (await _agenda(client, rec, MARTES)).json()
    assert j["ocupados_google"] == [{"profesional_id": mundo["ana"], "inicio": "2031-11-18T15:00:00-03:00",
                                     "fin": "2031-11-18T16:00:00-03:00"}]
    _, token_b = await crear_usuario_panel(session_factory, "bruno.odonto@turnos.test", ["odontologo"],
                                           profesional_id=mundo["bruno"])
    assert (await _agenda(client, bearer(token_b), MARTES)).json()["ocupados_google"] == []
    assert (await _agenda(client, rec, LUNES)).json()["ocupados_google"] == []  # otro día
    filtrada = (await _agenda(client, rec, MARTES, profesional_id=mundo["bruno"])).json()
    assert filtrada["ocupados_google"] == []


async def test_cada_turno_informa_el_estado_de_su_evento_y_si_tiene_conflicto(
        client, mundo, session_factory, rec, proveedor_gcal) -> None:
    conexion = await sembrar_conexion(session_factory, mundo["ana"])
    sincronizado = await insertar_turno(session_factory, mundo, local(MARTES, "09:00"))
    en_espera = await insertar_turno(session_factory, mundo, local(MARTES, "10:00"), estado="en_espera")
    sin_conexion = await insertar_turno(session_factory, mundo, local(MARTES, "09:00"), prof="bruno", sillon="s2")
    proveedor_gcal.crear_ocupado(local(MARTES, "09:00"), local(MARTES, "09:30"))  # se superpone con el sincronizado
    await ciclo(session_factory, proveedor_gcal, ahora=local(LUNES, "07:00"))
    por_id = {t["id"]: t for t in (await _agenda(client, rec, MARTES)).json()["turnos"]}
    assert por_id[sincronizado]["calendario"] == {"estado": "sincronizado", "conflicto_abierto": True}
    assert por_id[en_espera]["calendario"] == {"estado": "sin_evento", "conflicto_abierto": False}
    assert por_id[sin_conexion]["calendario"] == {"estado": "sin_evento", "conflicto_abierto": False}


async def test_los_campos_existentes_de_la_agenda_no_cambian(client, mundo, session_factory, rec) -> None:
    await insertar_turno(session_factory, mundo, local(MARTES, "09:00"))
    j = (await _agenda(client, rec, MARTES)).json()
    assert {"vista", "desde", "hasta", "turnos"} <= set(j) and j["ocupados_google"] == []
    assert {"id", "inicio", "fin", "estado", "bloquea_agenda", "origen", "profesional", "sillon", "tratamiento",
            "paciente_nombre", "paciente_telefono", "sena", "vence_en", "acciones"} <= set(j["turnos"][0])
