"""C-16 (2.1): ``acceso_clinico`` en ``GET /pacientes/{id}`` y en el alta/edición. PostgreSQL real. Datos sintéticos (R19)."""

from datetime import timedelta
from typing import Any

import pytest
from httpx import AsyncClient

from app.pacientes.alcance import VENTANA_ACCESO_CLINICO
from tests.clinica_helpers import (
    AHORA, Escenario, auditorias, crear_paciente, hace, sembrar_escenario, turno_de,
)
from tests.conftest import bearer

CUERPO_FICHA: dict[str, Any] = {"alergias": "x (sintético)", "medicacion": "", "antecedentes_medicos": "",
                                "observaciones": "", "version": 0}


@pytest.fixture
async def esc(session_factory, reloj) -> Escenario:  # type: ignore[no-untyped-def]
    reloj(AHORA)
    return await sembrar_escenario(session_factory)


async def _get(client: AsyncClient, token: str, paciente: int):  # type: ignore[no-untyped-def]
    return await client.get(f"/api/panel/pacientes/{paciente}", headers=bearer(token))


@pytest.mark.parametrize("rol", ["recepcion", "admin"])
async def test_recepcion_y_admin_reciben_total_y_pueden_escribir(session_factory, client: AsyncClient, esc: Escenario, rol: str) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    resp = await _get(client, getattr(esc, rol), paciente)
    assert resp.status_code == 200
    assert resp.json()["acceso_clinico"] == {"nivel": "total", "puede_escribir": True}


async def test_odontologa_con_atendido_reciente_recibe_clinico_completo_sin_contacto(session_factory, client: AsyncClient, esc: Escenario) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    await turno_de(session_factory, esc, paciente, hace(dias=60))
    cuerpo = (await _get(client, esc.ana, paciente)).json()
    assert cuerpo["acceso_clinico"] == {"nivel": "clinico_completo", "puede_escribir": True}
    assert "telefono" not in cuerpo and "email" not in cuerpo


async def test_limite_de_365_dias_exactos_vs_un_segundo_mas(session_factory, client: AsyncClient, esc: Escenario) -> None:  # type: ignore[no-untyped-def]
    en_limite = await crear_paciente(session_factory)
    vencido = await crear_paciente(session_factory)
    await turno_de(session_factory, esc, en_limite, AHORA - VENTANA_ACCESO_CLINICO)
    # El segundo atendido es de Bruno: dos turnos de la misma profesional a 1 s de distancia se solaparían (R5).
    await turno_de(session_factory, esc, vencido, AHORA - VENTANA_ACCESO_CLINICO - timedelta(seconds=1), prof="bruno")
    assert (await _get(client, esc.ana, en_limite)).json()["acceso_clinico"] == {
        "nivel": "clinico_completo", "puede_escribir": True}
    assert (await _get(client, esc.bruno, vencido)).json()["acceso_clinico"] == {
        "nivel": "clinico_lectura", "puede_escribir": False}
    put = await client.put(f"/api/panel/pacientes/{vencido}/ficha", json=CUERPO_FICHA, headers=bearer(esc.bruno))
    assert put.status_code == 403 and put.json()["motivo"] == "acceso_clinico_vencido"


async def test_atendido_de_13_meses_con_confirmado_futuro_es_completo(session_factory, client: AsyncClient, esc: Escenario) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    await turno_de(session_factory, esc, paciente, hace(dias=400))
    await turno_de(session_factory, esc, paciente, AHORA + timedelta(days=3), "confirmado")
    assert (await _get(client, esc.ana, paciente)).json()["acceso_clinico"] == {
        "nivel": "clinico_completo", "puede_escribir": True}


async def test_paciente_ajeno_403_sin_campo_y_sin_auditoria_de_lectura(session_factory, client: AsyncClient, esc: Escenario) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    resp = await _get(client, esc.ana, paciente)
    assert resp.status_code == 403 and resp.json()["motivo"] == "paciente_ajeno"
    assert "acceso_clinico" not in resp.text
    assert await auditorias(session_factory, "lectura_paciente") == []


async def test_alta_y_edicion_devuelven_acceso_total(session_factory, client: AsyncClient, esc: Escenario) -> None:  # type: ignore[no-untyped-def]
    cuerpo = {"nombre": "Mateo", "apellido": "Prueba", "dni": "99000002", "telefono": "+5491100000002"}
    alta = await client.post("/api/panel/pacientes", json=cuerpo, headers=bearer(esc.recepcion))
    assert alta.status_code == 201, alta.text
    assert alta.json()["acceso_clinico"] == {"nivel": "total", "puede_escribir": True}
    edicion = await client.put(f"/api/panel/pacientes/{alta.json()['id']}", json={**cuerpo, "apellido": "Prueba Dos"},
                               headers=bearer(esc.recepcion))
    assert edicion.status_code == 200, edicion.text
    assert edicion.json()["acceso_clinico"] == {"nivel": "total", "puede_escribir": True}
