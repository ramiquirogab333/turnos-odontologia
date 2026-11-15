"""C-16 (1.1): ``paciente_id`` en cada turno de la agenda del panel. PostgreSQL real. Datos sintéticos (R19)."""

from typing import Any

import pytest
from httpx import AsyncClient

from tests.clinica_helpers import Escenario, crear_paciente, sembrar_escenario
from tests.conftest import bearer
from tests.panel_helpers import LUNES, insertar_turno, local

URL = "/api/panel/agenda"
DIA = LUNES.isoformat()


@pytest.fixture
async def esc(session_factory, reloj) -> Escenario:  # type: ignore[no-untyped-def]
    reloj(local(LUNES, "07:00"))
    return await sembrar_escenario(session_factory)


async def _agenda(client: AsyncClient, token: str) -> list[dict[str, Any]]:
    resp = await client.get(URL, params={"vista": "dia", "fecha": DIA}, headers=bearer(token))
    assert resp.status_code == 200, resp.text
    return list(resp.json()["turnos"])


async def test_turno_vinculado_lo_ven_recepcion_y_odontologa_sin_telefono_para_ella(session_factory, client: AsyncClient, esc: Escenario) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    turno = await insertar_turno(session_factory, esc.mundo, local(LUNES, "09:00"), nombre="Lucía Ejemplo",
                                 paciente_id=paciente)
    [de_recepcion] = await _agenda(client, esc.recepcion)
    [de_ana] = await _agenda(client, esc.ana)
    assert de_recepcion["id"] == de_ana["id"] == turno
    assert de_recepcion["paciente_id"] == de_ana["paciente_id"] == paciente
    assert de_recepcion["paciente_telefono"] is not None
    assert de_ana["paciente_telefono"] is None


async def test_turno_de_otro_profesional_no_aparece_ni_filtra_su_paciente_id(session_factory, client: AsyncClient, esc: Escenario) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    await insertar_turno(session_factory, esc.mundo, local(LUNES, "09:00"), prof="bruno", sillon="s2",
                         paciente_id=paciente)
    assert await _agenda(client, esc.ana) == []
    resp = await client.get(URL, params={"vista": "dia", "fecha": DIA}, headers=bearer(esc.ana))
    assert f'"paciente_id":{paciente}' not in resp.text.replace(" ", "")


async def test_turno_sin_vinculo_trae_null_y_al_vincular_trae_el_id_con_el_mismo_nombre(session_factory, client: AsyncClient, esc: Escenario) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory, nombre="Mateo", apellido="Prueba", dni="99000002")
    turno = await insertar_turno(session_factory, esc.mundo, local(LUNES, "10:00"), nombre="Carlos Sintético")
    [antes] = await _agenda(client, esc.recepcion)
    assert antes["paciente_id"] is None
    vinc = await client.put(f"/api/panel/turnos/{turno}/paciente", json={"paciente_id": paciente},
                            headers=bearer(esc.recepcion))
    assert vinc.status_code == 200, vinc.text
    [despues] = await _agenda(client, esc.recepcion)
    assert despues["paciente_id"] == paciente
    assert despues["paciente_nombre"] == antes["paciente_nombre"] == "Carlos Sintético"
