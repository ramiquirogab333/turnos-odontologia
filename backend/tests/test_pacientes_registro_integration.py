"""C-11 (grupo 4): alta, búsqueda, consulta/edición de pacientes y vínculo con turnos. Datos sintéticos (R19)."""

import json
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.core import Paciente
from app.turnos.models import Turno
from tests.clinica_helpers import (
    AHORA, Escenario, auditorias, contar, crear_obra_social, crear_paciente, sembrar_escenario, turno_de,
)
from tests.conftest import bearer
from tests.panel_helpers import insertar_turno, local, LUNES

ALTA: dict[str, Any] = {"nombre": "Lucía", "apellido": "Ejemplo", "dni": "99000001", "telefono": "+5491100000001"}


@pytest.fixture
async def esc(session_factory) -> Escenario:  # type: ignore[no-untyped-def]
    return await sembrar_escenario(session_factory)


# --- 4.1 Alta y búsqueda por DNI -------------------------------------------------------------------------------

async def test_alta_valida_responde_201_y_audita_sin_datos_personales(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    swiss = await crear_obra_social(session_factory)
    resp = await client.post("/api/panel/pacientes", json={**ALTA, "obra_social_id": swiss,
                                                           "numero_afiliado": "SM-SINT-0001"},
                             headers=bearer(esc.recepcion))
    assert resp.status_code == 201, resp.text
    cuerpo = resp.json()
    assert cuerpo["dni"] == "99000001" and cuerpo["obra_social"]["id"] == swiss
    [registro] = await auditorias(session_factory, "alta_paciente")
    assert (registro.usuario_id, registro.entidad, registro.entidad_id) == (esc.recepcion_id, "paciente",
                                                                              str(cuerpo["id"]))
    volcado = json.dumps(registro.datos_despues) + json.dumps(registro.datos_antes)
    for prohibido in ("Lucía", "Ejemplo", "99000001", "+5491100000001", "SM-SINT-0001"):
        assert prohibido not in volcado


async def test_alta_con_dni_repetido_409_y_odontologa_403_sin_efectos(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await crear_paciente(session_factory, dni="99000001")
    repetido = await client.post("/api/panel/pacientes", json=ALTA, headers=bearer(esc.recepcion))
    assert repetido.status_code == 409 and repetido.json()["motivo"] == "dni_duplicado"
    nuevo = await client.post("/api/panel/pacientes", json={**ALTA, "dni": "99000002"}, headers=bearer(esc.ana))
    assert nuevo.status_code == 403
    assert await contar(session_factory, "paciente") == 1
    assert await auditorias(session_factory, "alta_paciente") == []


async def test_alta_con_dni_de_7_digitos_ok_y_con_obra_social_inactiva_422(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    activa = await crear_obra_social(session_factory, "SWISS", "Swiss Medical")
    inactiva = await crear_obra_social(session_factory, "VIEJA", "Prepaga Vieja", activa=False)
    ok = await client.post("/api/panel/pacientes", json={**ALTA, "dni": "9900001", "obra_social_id": activa},
                           headers=bearer(esc.recepcion))
    assert ok.status_code == 201
    mal = await client.post("/api/panel/pacientes", json={**ALTA, "dni": "99000009", "obra_social_id": inactiva},
                            headers=bearer(esc.recepcion))
    assert mal.status_code == 422 and mal.json()["motivo"] == "obra_social_inactiva"
    inexistente = await client.post("/api/panel/pacientes", json={**ALTA, "dni": "99000008", "obra_social_id": 99999},
                                    headers=bearer(esc.recepcion))
    assert inexistente.status_code == 422 and inexistente.json()["motivo"] == "obra_social_inactiva"
    assert await contar(session_factory, "paciente") == 1


async def test_alta_sin_token_401_y_campos_extra_422(client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    assert (await client.post("/api/panel/pacientes", json=ALTA)).status_code == 401
    extra = await client.post("/api/panel/pacientes", json={**ALTA, "notas": "x"}, headers=bearer(esc.recepcion))
    assert extra.status_code == 422


async def test_busqueda_por_dni_existente_inexistente_y_mal_formado(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await crear_paciente(session_factory, dni="99000001")
    h = bearer(esc.recepcion)
    uno = await client.get("/api/panel/pacientes", params={"dni": "99000001"}, headers=h)
    assert uno.status_code == 200 and [p["dni"] for p in uno.json()] == ["99000001"]
    vacio = await client.get("/api/panel/pacientes", params={"dni": "99000099"}, headers=h)
    assert vacio.status_code == 200 and vacio.json() == []
    for malo in ("12ab", "123456", "123456789"):
        assert (await client.get("/api/panel/pacientes", params={"dni": malo}, headers=h)).status_code == 422
    assert (await client.get("/api/panel/pacientes", headers=h)).status_code == 422


async def test_odontologa_no_puede_buscar_por_dni(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await crear_paciente(session_factory, dni="99000001")
    resp = await client.get("/api/panel/pacientes", params={"dni": "99000001"}, headers=bearer(esc.ana))
    assert resp.status_code == 403 and "99000001" not in resp.text


# --- 4.3 Consulta y edición ------------------------------------------------------------------------------------

async def test_recepcion_edita_el_telefono_y_se_audita_solo_el_nombre_del_campo(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory, dni="99000001")
    cuerpo = {**ALTA, "telefono": "+5491100000002", "email": "lucia@ejemplo.test"}
    resp = await client.put(f"/api/panel/pacientes/{paciente}", json=cuerpo, headers=bearer(esc.recepcion))
    assert resp.status_code == 200 and resp.json()["telefono"] == "+5491100000002"
    [registro] = await auditorias(session_factory, "edicion_paciente")
    assert registro.datos_despues == {"campos": ["telefono"]}
    assert "+5491100000002" not in json.dumps(registro.datos_despues)


async def test_editar_a_un_dni_de_otro_paciente_409(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await crear_paciente(session_factory, dni="99000002")
    paciente = await crear_paciente(session_factory, dni="99000001")
    resp = await client.put(f"/api/panel/pacientes/{paciente}", json={**ALTA, "dni": "99000002"},
                            headers=bearer(esc.recepcion))
    assert resp.status_code == 409 and resp.json()["motivo"] == "dni_duplicado"


async def test_odontologa_no_edita_ni_a_su_paciente_y_el_paciente_no_cambia(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory, dni="99000001")
    await turno_de(session_factory, esc, paciente, AHORA.replace(year=2026, month=9))
    resp = await client.put(f"/api/panel/pacientes/{paciente}", json={**ALTA, "telefono": "+5491100000077"},
                            headers=bearer(esc.ana))
    assert resp.status_code == 403
    async with session_factory() as s:
        assert (await s.get(Paciente, paciente)).telefono == "+5491100000001"  # type: ignore[union-attr]


async def test_odontologa_ajena_lee_403_paciente_ajeno(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    await turno_de(session_factory, esc, paciente, AHORA.replace(day=20), "confirmado")
    resp = await client.get(f"/api/panel/pacientes/{paciente}", headers=bearer(esc.ana))
    assert resp.status_code == 403 and resp.json()["motivo"] == "paciente_ajeno"


async def test_odontologa_propia_ve_dni_y_afiliado_pero_no_telefono_ni_email(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    swiss = await crear_obra_social(session_factory)
    paciente = await crear_paciente(session_factory, dni="99000001", obra_social_id=swiss,
                                    numero_afiliado="SM-SINT-0001")
    await turno_de(session_factory, esc, paciente, AHORA.replace(month=9))
    resp = await client.get(f"/api/panel/pacientes/{paciente}", headers=bearer(esc.ana))
    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    assert set(cuerpo) == {"id", "nombre", "apellido", "dni", "obra_social", "numero_afiliado"}
    assert cuerpo["dni"] == "99000001" and cuerpo["numero_afiliado"] == "SM-SINT-0001"
    assert "+5491100000001" not in resp.text and "lucia@ejemplo.test" not in resp.text


async def test_recepcion_y_admin_reciben_la_respuesta_completa_y_404_si_no_existe(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    for token in (esc.recepcion, esc.admin):
        resp = await client.get(f"/api/panel/pacientes/{paciente}", headers=bearer(token))
        assert resp.status_code == 200
        assert {"telefono", "email", "dni", "numero_afiliado"} <= set(resp.json())
    assert (await client.get("/api/panel/pacientes/987654", headers=bearer(esc.recepcion))).status_code == 404
    assert (await client.get("/api/panel/pacientes/987654", headers=bearer(esc.ana))).status_code == 404


# --- 4.4 Vínculo de un turno con su paciente ------------------------------------------------------------------

async def _turno_manual(session_factory, esc: Escenario, **extra: Any) -> int:  # type: ignore[no-untyped-def]
    return await insertar_turno(session_factory, esc.mundo, local(LUNES, "09:00"), origen="manual",
                                nombre="Lucía Ejemplo", telefono="+5491100000001", con_codigo=False, **extra)


async def test_vincular_un_turno_manual_no_cambia_estado_ni_contacto(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    turno_id = await _turno_manual(session_factory, esc)
    resp = await client.put(f"/api/panel/turnos/{turno_id}/paciente", json={"paciente_id": paciente},
                            headers=bearer(esc.recepcion))
    assert resp.status_code == 200 and resp.json() == {"turno_id": turno_id, "paciente_id": paciente}
    async with session_factory() as s:
        t = (await s.execute(select(Turno).where(Turno.id == turno_id))).scalar_one()
    assert (t.paciente_id, t.estado, t.contacto_nombre, t.contacto_telefono) == (
        paciente, "reservado", "Lucía Ejemplo", "+5491100000001")
    [registro] = await auditorias(session_factory, "vinculo_turno_paciente")
    assert registro.entidad == "turno" and registro.entidad_id == str(turno_id)


async def test_vincular_con_turno_o_paciente_inexistente_404_y_odontologa_403(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    turno_id = await _turno_manual(session_factory, esc)
    h = bearer(esc.recepcion)
    assert (await client.put("/api/panel/turnos/987654/paciente", json={"paciente_id": paciente},
                             headers=h)).status_code == 404
    assert (await client.put(f"/api/panel/turnos/{turno_id}/paciente", json={"paciente_id": 987654},
                             headers=h)).status_code == 404
    assert (await client.put(f"/api/panel/turnos/{turno_id}/paciente", json={"paciente_id": paciente},
                             headers=bearer(esc.ana))).status_code == 403
    async with session_factory() as s:
        assert (await s.get(Turno, turno_id)).paciente_id is None  # type: ignore[union-attr]
    assert await auditorias(session_factory, "vinculo_turno_paciente") == []


async def test_corregir_un_vinculo_equivocado_audita_ambos_ids(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    mateo = await crear_paciente(session_factory, nombre="Mateo", apellido="Prueba", dni="99000012")
    lucia = await crear_paciente(session_factory)
    turno_id = await _turno_manual(session_factory, esc, paciente_id=mateo)
    resp = await client.put(f"/api/panel/turnos/{turno_id}/paciente", json={"paciente_id": lucia},
                            headers=bearer(esc.recepcion))
    assert resp.status_code == 200
    [registro] = await auditorias(session_factory, "vinculo_turno_paciente")
    assert registro.datos_despues == {"paciente_anterior_id": mateo, "paciente_nuevo_id": lucia}
