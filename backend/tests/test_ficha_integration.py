"""C-11 (grupo 5): ficha clínica, versión, alcance por odontóloga, auditoría y ventana de O16. Datos sintéticos (R19)."""

import asyncio
import json
from datetime import timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.pacientes.alcance import VENTANA_ACCESO_CLINICO
from app.pacientes.models import Ficha
from tests.clinica_helpers import (
    AHORA, Escenario, auditorias, contar, crear_paciente, hace, sembrar_escenario, turno_de,
)
from tests.conftest import bearer

ANTECEDENTES: dict[str, Any] = {"alergias": "penicilina (dato sintético)", "medicacion": "ninguna",
                                "antecedentes_medicos": "", "observaciones": ""}


def _cuerpo(version: int, **cambios: str) -> dict[str, Any]:
    return {**ANTECEDENTES, **cambios, "version": version}


@pytest.fixture
async def esc(session_factory, reloj) -> Escenario:  # type: ignore[no-untyped-def]
    reloj(AHORA)
    return await sembrar_escenario(session_factory)


async def _ficha(session_factory, paciente_id: int) -> Ficha | None:  # type: ignore[no-untyped-def]
    async with session_factory() as s:
        return (await s.execute(select(Ficha).where(Ficha.paciente_id == paciente_id))).scalar_one_or_none()


async def _propia(session_factory, esc: Escenario, paciente_id: int, dias: int = 60) -> None:  # type: ignore[no-untyped-def]
    """La Dra. Ana atendió al paciente hace ``dias`` días (acceso completo por defecto)."""
    await turno_de(session_factory, esc, paciente_id, hace(dias=dias))


# --- 5.1 / 5.2 Consulta ---------------------------------------------------------------------------------------

async def test_ficha_con_antecedentes_e_historia_ordenada_sin_contacto(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    async with session_factory() as s:
        s.add(Ficha(paciente_id=paciente, alergias="penicilina (dato sintético)", version=1))
        await s.commit()
    antiguo = await turno_de(session_factory, esc, paciente, hace(dias=60))
    futuro = await turno_de(session_factory, esc, paciente, AHORA + timedelta(days=2), "reservado")
    otra = await turno_de(session_factory, esc, paciente, hace(dias=30), "atendido", prof="bruno")
    await turno_de(session_factory, esc, paciente, hace(dias=1), "en_espera", vence=hace(dias=1))  # vencida: no figura
    resp = await client.get(f"/api/panel/pacientes/{paciente}/ficha", headers=bearer(esc.recepcion))
    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    assert cuerpo["alergias"] == "penicilina (dato sintético)" and cuerpo["version"] == 1
    assert [t["turno_id"] for t in cuerpo["historia"]] == [futuro, otra, antiguo]
    assert {t["profesional"]["nombre"] for t in cuerpo["historia"]} == {"Dra. Ana Ficticia", "Dr. Bruno Ejemplo"}
    assert "+5491100000001" not in resp.text and "lucia@ejemplo.test" not in resp.text
    assert len(await auditorias(session_factory, "lectura_ficha")) == 1


async def test_ficha_de_paciente_inexistente_404_sin_auditoria(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    resp = await client.get("/api/panel/pacientes/987654/ficha", headers=bearer(esc.recepcion))
    assert resp.status_code == 404
    assert await auditorias(session_factory) == []


async def test_paciente_sin_ficha_devuelve_vacia_con_version_cero(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    resp = await client.get(f"/api/panel/pacientes/{paciente}/ficha", headers=bearer(esc.recepcion))
    assert resp.status_code == 200
    assert resp.json() == {"paciente_id": paciente, "alergias": "", "medicacion": "", "antecedentes_medicos": "",
                           "observaciones": "", "version": 0, "actualizado_por": None, "historia": []}
    assert await _ficha(session_factory, paciente) is None  # leer no crea la fila


# --- 5.3 Edición con control de versión ---------------------------------------------------------------------

async def test_version_avanza_0_1_2_y_una_version_vieja_da_409_sin_cambios(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    url, h = f"/api/panel/pacientes/{paciente}/ficha", bearer(esc.recepcion)
    primera = await client.put(url, json=_cuerpo(0), headers=h)
    assert primera.status_code == 200 and primera.json()["version"] == 1
    assert primera.json()["actualizado_por"] == esc.recepcion_id
    segunda = await client.put(url, json=_cuerpo(1, medicacion="ibuprofeno"), headers=h)
    assert segunda.status_code == 200 and segunda.json()["version"] == 2
    vieja = await client.put(url, json=_cuerpo(1, medicacion="otra cosa"), headers=h)
    assert vieja.status_code == 409 and vieja.json()["motivo"] == "version_desactualizada"
    repetida_cero = await client.put(url, json=_cuerpo(0), headers=h)  # ya existe: version 0 ya no sirve
    assert repetida_cero.status_code == 409
    ficha = await _ficha(session_factory, paciente)
    assert (ficha.version, ficha.medicacion) == (2, "ibuprofeno")  # type: ignore[union-attr]


@pytest.mark.parametrize("largo,codigo", [(2000, 200), (2001, 422)])
async def test_limite_de_2000_caracteres(session_factory, client: AsyncClient, esc, largo: int, codigo: int) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    resp = await client.put(f"/api/panel/pacientes/{paciente}/ficha", json=_cuerpo(0, observaciones="o" * largo),
                            headers=bearer(esc.recepcion))
    assert resp.status_code == codigo
    assert (await _ficha(session_factory, paciente) is not None) is (codigo == 200)


async def test_editar_ficha_de_paciente_inexistente_404(client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    resp = await client.put("/api/panel/pacientes/987654/ficha", json=_cuerpo(0), headers=bearer(esc.recepcion))
    assert resp.status_code == 404


# --- 5.4 Escritura de la odontóloga (O4) ---------------------------------------------------------------------

async def test_recepcion_carga_y_la_odontologa_propia_corrige(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    await _propia(session_factory, esc, paciente)
    url = f"/api/panel/pacientes/{paciente}/ficha"
    assert (await client.put(url, json=_cuerpo(0), headers=bearer(esc.recepcion))).status_code == 200
    resp = await client.put(url, json=_cuerpo(1, alergias="látex (dato sintético)"), headers=bearer(esc.ana))
    assert resp.status_code == 200, resp.text
    assert (resp.json()["version"], resp.json()["actualizado_por"]) == (2, esc.ana_id)
    assert (await _ficha(session_factory, paciente)).actualizado_por == esc.ana_id  # type: ignore[union-attr]


async def test_odontologa_ajena_403_sin_cambios_ni_auditoria(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    await turno_de(session_factory, esc, paciente, AHORA + timedelta(days=1), "confirmado")
    async with session_factory() as s:
        s.add(Ficha(paciente_id=paciente, alergias="original", version=3))
        await s.commit()
    resp = await client.put(f"/api/panel/pacientes/{paciente}/ficha", json=_cuerpo(3), headers=bearer(esc.ana))
    assert resp.status_code == 403 and resp.json()["motivo"] == "paciente_ajeno"
    ficha = await _ficha(session_factory, paciente)
    assert (ficha.version, ficha.alergias) == (3, "original")  # type: ignore[union-attr]
    assert await auditorias(session_factory) == []


@pytest.mark.parametrize("version_inicial", [0, 1])
async def test_edicion_simultanea_entre_roles_un_200_y_un_409(session_factory, client: AsyncClient, esc, version_inicial: int) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    await _propia(session_factory, esc, paciente)
    if version_inicial:
        async with session_factory() as s:
            s.add(Ficha(paciente_id=paciente, version=version_inicial))
            await s.commit()
    url = f"/api/panel/pacientes/{paciente}/ficha"
    r1, r2 = await asyncio.gather(
        client.put(url, json=_cuerpo(version_inicial, alergias="de recepción"), headers=bearer(esc.recepcion)),
        client.put(url, json=_cuerpo(version_inicial, alergias="de la odontóloga"), headers=bearer(esc.ana)))
    assert sorted([r1.status_code, r2.status_code]) == [200, 409], (r1.text, r2.text)
    perdedora = r1 if r1.status_code == 409 else r2
    assert perdedora.json()["motivo"] == "version_desactualizada"
    assert (await _ficha(session_factory, paciente)).version == version_inicial + 1  # type: ignore[union-attr]


# --- 5.5 Alcance y auditoría ---------------------------------------------------------------------------------

async def test_acceso_denegado_en_ficha_odontograma_y_presupuestos_sin_registro_de_auditoria(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    mateo = await crear_paciente(session_factory, nombre="Mateo", apellido="Prueba", dni="99000012")
    await turno_de(session_factory, esc, mateo, AHORA + timedelta(days=1), "confirmado")
    await turno_de(session_factory, esc, mateo, hace(dias=30), "ausente")
    await turno_de(session_factory, esc, mateo, hace(dias=10), "atendido", prof="bruno")
    h = bearer(esc.ana)
    for ruta in ("ficha", "odontograma", "odontograma/historial", "presupuestos"):
        resp = await client.get(f"/api/panel/pacientes/{mateo}/{ruta}", headers=h)
        assert (resp.status_code, resp.json()["motivo"]) == (403, "paciente_ajeno"), ruta
    assert (await client.put(f"/api/panel/pacientes/{mateo}/ficha", json=_cuerpo(0), headers=h)).status_code == 403
    assert await auditorias(session_factory) == []


async def test_atendido_hace_un_ano_puede_leer_y_la_primera_visita_abre_al_marcar_atendido(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    vieja = await crear_paciente(session_factory)
    await turno_de(session_factory, esc, vieja, hace(dias=400))
    assert (await client.get(f"/api/panel/pacientes/{vieja}/ficha", headers=bearer(esc.ana))).status_code == 200

    nueva = await crear_paciente(session_factory, nombre="Mateo", apellido="Prueba", dni="99000012")
    turno_id = await turno_de(session_factory, esc, nueva, AHORA + timedelta(hours=1), "reservado")
    assert (await client.get(f"/api/panel/pacientes/{nueva}/ficha", headers=bearer(esc.ana))).status_code == 403
    marcado = await client.post(f"/api/panel/turnos/{turno_id}/atendido", headers=bearer(esc.recepcion))
    assert marcado.status_code == 200
    assert (await client.get(f"/api/panel/pacientes/{nueva}/ficha", headers=bearer(esc.ana))).status_code == 200


async def test_lectura_y_edicion_de_la_odontologa_quedan_auditadas_sin_contenido_clinico(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    await _propia(session_factory, esc, paciente)
    url, h = f"/api/panel/pacientes/{paciente}/ficha", bearer(esc.ana)
    assert (await client.get(url, headers=h)).status_code == 200
    resp = await client.put(url, json=_cuerpo(0, alergias="látex (dato sintético)"), headers=h)
    assert resp.status_code == 200
    [lectura] = await auditorias(session_factory, "lectura_ficha")
    [edicion] = await auditorias(session_factory, "edicion_ficha")
    for registro in (lectura, edicion):
        assert (registro.usuario_id, registro.entidad, registro.entidad_id) == (esc.ana_id, "ficha", str(paciente))
    volcado = json.dumps(edicion.datos_despues, ensure_ascii=False)
    assert "látex" not in volcado and "penicilina" not in volcado
    assert edicion.datos_despues == {"campos": ["alergias", "medicacion"], "version": 1}


# --- 5.6 Ventana de acceso clínico (O16) -----------------------------------------------------------------------

async def test_atendido_hace_11_meses_escribe(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    await _propia(session_factory, esc, paciente, dias=335)
    resp = await client.put(f"/api/panel/pacientes/{paciente}/ficha", json=_cuerpo(0), headers=bearer(esc.ana))
    assert resp.status_code == 200


async def test_atendido_hace_13_meses_lee_pero_no_escribe(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    await _propia(session_factory, esc, paciente, dias=395)
    url, h = f"/api/panel/pacientes/{paciente}/ficha", bearer(esc.ana)
    assert (await client.get(url, headers=h)).status_code == 200
    resp = await client.put(url, json=_cuerpo(0), headers=h)
    assert (resp.status_code, resp.json()["motivo"]) == (403, "acceso_clinico_vencido")
    assert await _ficha(session_factory, paciente) is None
    assert await auditorias(session_factory, "edicion_ficha") == []
    assert len(await auditorias(session_factory, "lectura_ficha")) == 1


async def test_13_meses_mas_confirmado_futuro_escribe(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    await _propia(session_factory, esc, paciente, dias=395)
    await turno_de(session_factory, esc, paciente, AHORA + timedelta(days=7), "confirmado")
    resp = await client.put(f"/api/panel/pacientes/{paciente}/ficha", json=_cuerpo(0), headers=bearer(esc.ana))
    assert resp.status_code == 200


async def test_solo_turno_futuro_nunca_atendido_es_ajeno_en_get_y_put(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    await turno_de(session_factory, esc, paciente, AHORA + timedelta(days=1), "confirmado")
    url, h = f"/api/panel/pacientes/{paciente}/ficha", bearer(esc.ana)
    assert (await client.get(url, headers=h)).json()["motivo"] == "paciente_ajeno"
    assert (await client.put(url, json=_cuerpo(0), headers=h)).json()["motivo"] == "paciente_ajeno"


@pytest.mark.parametrize("segundos_extra,codigo,motivo", [(0, 200, None), (1, 403, "acceso_clinico_vencido")])
async def test_borde_de_365_dias_en_la_ficha(session_factory, client: AsyncClient, esc, segundos_extra: int,  # type: ignore[no-untyped-def]
                                              codigo: int, motivo: str | None) -> None:
    paciente = await crear_paciente(session_factory)
    await turno_de(session_factory, esc, paciente, AHORA - VENTANA_ACCESO_CLINICO - timedelta(seconds=segundos_extra))
    resp = await client.put(f"/api/panel/pacientes/{paciente}/ficha", json=_cuerpo(0), headers=bearer(esc.ana))
    assert resp.status_code == codigo
    if motivo:
        assert resp.json()["motivo"] == motivo


async def test_sin_ficha_ni_efectos_en_otras_tablas_tras_un_rechazo(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    await _propia(session_factory, esc, paciente, dias=395)
    await client.put(f"/api/panel/pacientes/{paciente}/ficha", json=_cuerpo(0), headers=bearer(esc.ana))
    assert await contar(session_factory, "ficha") == 0


# --- 9.6 La odontóloga marca atendido y gana (o no) el acceso clínico (O15) ----------------------------------

async def test_primera_visita_la_odontologa_marca_atendido_y_gana_lectura_y_edicion(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    mateo = await crear_paciente(session_factory, nombre="Mateo", apellido="Prueba", dni="99000012")
    turno_id = await turno_de(session_factory, esc, mateo, AHORA + timedelta(hours=1), "reservado")
    url, h = f"/api/panel/pacientes/{mateo}/ficha", bearer(esc.ana)
    assert (await client.get(url, headers=h)).json()["motivo"] == "paciente_ajeno"
    assert (await client.post(f"/api/panel/turnos/{turno_id}/atendido", headers=h)).status_code == 200
    assert (await client.get(url, headers=h)).status_code == 200
    assert (await client.put(url, json=_cuerpo(0), headers=h)).status_code == 200  # acceso completo: el atendido es de hoy
    [marcado] = [a for a in await auditorias(session_factory)
                 if (a.datos_despues or {}).get("origen") == "marcado_atendido_panel"]
    assert marcado.usuario_id == esc.ana_id
    lecturas = await auditorias(session_factory, "lectura_ficha")
    assert [a.usuario_id for a in lecturas] == [esc.ana_id]  # la lectura rechazada no deja registro


async def test_turno_manual_sin_paciente_vinculado_no_da_acceso_hasta_que_recepcion_lo_vincula(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    mateo = await crear_paciente(session_factory, nombre="Mateo", apellido="Prueba", dni="99000012")
    turno_id = await turno_de(session_factory, esc, None, AHORA + timedelta(hours=1), "reservado", origen="manual",
                              nombre="Mateo Prueba", telefono="+5491100000012", con_codigo=False)
    url, h = f"/api/panel/pacientes/{mateo}/ficha", bearer(esc.ana)
    assert (await client.post(f"/api/panel/turnos/{turno_id}/atendido", headers=h)).status_code == 200
    assert (await client.get(url, headers=h)).json()["motivo"] == "paciente_ajeno"
    vinculo = await client.put(f"/api/panel/turnos/{turno_id}/paciente", json={"paciente_id": mateo},
                               headers=bearer(esc.recepcion))
    assert vinculo.status_code == 200
    assert (await client.get(url, headers=h)).status_code == 200  # sin volver a marcar el turno


async def test_atendido_sin_vincular_no_cuenta_para_la_ventana_de_escritura(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    lucia = await crear_paciente(session_factory)
    await turno_de(session_factory, esc, lucia, hace(dias=395))
    turno_id = await turno_de(session_factory, esc, None, AHORA + timedelta(hours=1), "reservado", origen="manual",
                              nombre="Lucía Ejemplo", telefono="+5491100000001", con_codigo=False)
    url, h = f"/api/panel/pacientes/{lucia}/ficha", bearer(esc.ana)
    assert (await client.post(f"/api/panel/turnos/{turno_id}/atendido", headers=h)).status_code == 200
    sin_vincular = await client.put(url, json=_cuerpo(0), headers=h)
    assert (sin_vincular.status_code, sin_vincular.json()["motivo"]) == (403, "acceso_clinico_vencido")
    await client.put(f"/api/panel/turnos/{turno_id}/paciente", json={"paciente_id": lucia},
                     headers=bearer(esc.recepcion))
    assert (await client.put(url, json=_cuerpo(0), headers=h)).status_code == 200
