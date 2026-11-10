"""C-11 (grupo 6): odontograma solo de alta, vigente, historial y ventana de O16. Datos sintéticos (R19)."""

import json
from datetime import timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.clinica.models import OdontogramaRegistro
from tests.clinica_helpers import AHORA, Escenario, auditorias, contar, crear_paciente, hace, sembrar_escenario, turno_de
from tests.conftest import bearer


@pytest.fixture
async def esc(session_factory, reloj) -> Escenario:  # type: ignore[no-untyped-def]
    reloj(AHORA)
    return await sembrar_escenario(session_factory)


def _lote(*registros: dict[str, Any]) -> dict[str, Any]:
    return {"registros": list(registros)}


CARIES_16O = {"pieza": 16, "cara": "O", "estado": "caries"}
AUSENTE_36 = {"pieza": 36, "estado": "ausente"}
OBTURADO_46M = {"pieza": 46, "cara": "M", "estado": "obturado"}


def _url(paciente: int, ruta: str = "") -> str:
    return f"/api/panel/pacientes/{paciente}/odontograma{ruta}"


# --- 6.1 / 6.2 Registro por recepción ---------------------------------------------------------------------------

async def test_recepcion_registra_un_lote_de_tres_con_auditoria_sin_estados(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    resp = await client.post(_url(paciente), json=_lote(CARIES_16O, AUSENTE_36, OBTURADO_46M),
                             headers=bearer(esc.recepcion))
    assert resp.status_code == 201, resp.text
    registros = resp.json()["registros"]
    assert [(r["pieza"], r["cara"], r["estado"]) for r in registros] == [
        (16, "O", "caries"), (36, None, "ausente"), (46, "M", "obturado")]
    assert all(r["registrado_por"] == esc.recepcion_id for r in registros)
    [auditoria] = await auditorias(session_factory, "registro_odontograma")
    assert (auditoria.usuario_id, auditoria.entidad, auditoria.entidad_id) == (
        esc.recepcion_id, "odontograma", str(paciente))
    assert auditoria.datos_despues == {"cantidad": 3}
    assert "caries" not in json.dumps(auditoria.datos_despues)


async def test_un_registro_invalido_en_el_lote_rechaza_todo(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    resp = await client.post(_url(paciente), json=_lote(CARIES_16O, AUSENTE_36, {"pieza": 99, "estado": "ausente"}),
                             headers=bearer(esc.recepcion))
    assert resp.status_code == 422
    assert await contar(session_factory, "odontograma_registro") == 0
    assert await auditorias(session_factory) == []


@pytest.mark.parametrize("n,codigo", [(64, 201), (65, 422), (0, 422)])
async def test_tamano_del_lote(session_factory, client: AsyncClient, esc, n: int, codigo: int) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    resp = await client.post(_url(paciente), json=_lote(*[CARIES_16O] * n), headers=bearer(esc.recepcion))
    assert resp.status_code == codigo
    assert await contar(session_factory, "odontograma_registro") == (n if codigo == 201 else 0)


@pytest.mark.parametrize("pieza,codigo", [(55, 201), (56, 422), (18, 201), (19, 422)])
async def test_bordes_de_denticion(session_factory, client: AsyncClient, esc, pieza: int, codigo: int) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    resp = await client.post(_url(paciente), json=_lote({"pieza": pieza, "estado": "ausente"}),
                             headers=bearer(esc.admin))
    assert resp.status_code == codigo


@pytest.mark.parametrize("registro", [{"pieza": 16, "estado": "caries"}, {"pieza": 16, "cara": "O", "estado": "corona"}])
async def test_combinaciones_cara_estado_invalidas_422(session_factory, client: AsyncClient, esc, registro: dict[str, Any]) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    assert (await client.post(_url(paciente), json=_lote(registro), headers=bearer(esc.recepcion))).status_code == 422


async def test_paciente_inexistente_404_y_sin_token_401(client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    assert (await client.post(_url(987654), json=_lote(CARIES_16O), headers=bearer(esc.recepcion))).status_code == 404
    assert (await client.post(_url(987654), json=_lote(CARIES_16O))).status_code == 401


# --- 6.3 Escritura de la odontóloga (O4) --------------------------------------------------------------------

async def test_odontologa_propia_registra_y_queda_su_usuario(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    await turno_de(session_factory, esc, paciente, hace(dias=30))
    resp = await client.post(_url(paciente), json=_lote(CARIES_16O, AUSENTE_36, OBTURADO_46M), headers=bearer(esc.ana))
    assert resp.status_code == 201
    assert {r["registrado_por"] for r in resp.json()["registros"]} == {esc.ana_id}
    [auditoria] = await auditorias(session_factory, "registro_odontograma")
    assert (auditoria.usuario_id, auditoria.datos_despues) == (esc.ana_id, {"cantidad": 3})


async def test_odontologa_ajena_403_cero_registros_y_sin_auditoria(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    mateo = await crear_paciente(session_factory, nombre="Mateo", apellido="Prueba", dni="99000012")
    await turno_de(session_factory, esc, mateo, AHORA + timedelta(days=1), "confirmado")
    resp = await client.post(_url(mateo), json=_lote(CARIES_16O), headers=bearer(esc.ana))
    assert (resp.status_code, resp.json()["motivo"]) == (403, "paciente_ajeno")
    assert await contar(session_factory, "odontograma_registro") == 0
    assert await auditorias(session_factory) == []


# --- 6.4 Vigente e historial ---------------------------------------------------------------------------------

async def test_caries_luego_obturado_muestra_solo_obturado_a_la_odontologa(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    await turno_de(session_factory, esc, paciente, hace(dias=30))
    await client.post(_url(paciente), json=_lote(CARIES_16O), headers=bearer(esc.recepcion))
    await client.post(_url(paciente), json=_lote({"pieza": 16, "cara": "O", "estado": "obturado"}),
                      headers=bearer(esc.recepcion))
    resp = await client.get(_url(paciente), headers=bearer(esc.ana))
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"paciente_id": paciente,
                           "piezas": [{"pieza": 16, "estado_pieza": None, "caras": {"O": "obturado"}}]}
    assert len(await auditorias(session_factory, "lectura_odontograma")) == 1


async def test_pieza_vuelta_a_sana_no_muestra_hallazgos_pero_el_historial_conserva_todo(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    h = bearer(esc.recepcion)
    await client.post(_url(paciente), json=_lote({"pieza": 26, "estado": "endodoncia"}), headers=h)
    await client.post(_url(paciente), json=_lote({"pieza": 26, "cara": "M", "estado": "caries"}), headers=h)
    await client.post(_url(paciente), json=_lote({"pieza": 26, "estado": "sano"}), headers=h)
    assert (await client.get(_url(paciente), headers=h)).json()["piezas"] == []
    historial = await client.get(_url(paciente, "/historial"), headers=h)
    assert [r["estado"] for r in historial.json()["registros"]] == ["sano", "caries", "endodoncia"]


async def test_historial_paginado_con_cursor_y_limites(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    h = bearer(esc.recepcion)
    for pieza in (11, 12, 13, 14, 15):
        await client.post(_url(paciente), json=_lote({"pieza": pieza, "estado": "ausente"}), headers=h)
    primera = (await client.get(_url(paciente, "/historial"), params={"limite": 2}, headers=h)).json()
    assert [r["pieza"] for r in primera["registros"]] == [15, 14]
    segunda = (await client.get(_url(paciente, "/historial"),
                                params={"limite": 2, "antes_de_id": primera["siguiente_antes_de_id"]}, headers=h)).json()
    assert [r["pieza"] for r in segunda["registros"]] == [13, 12]
    ultima = (await client.get(_url(paciente, "/historial"),
                               params={"limite": 2, "antes_de_id": segunda["siguiente_antes_de_id"]}, headers=h)).json()
    assert [r["pieza"] for r in ultima["registros"]] == [11] and ultima["siguiente_antes_de_id"] is None
    todo = await client.get(_url(paciente, "/historial"), params={"limite": 200}, headers=h)
    assert todo.status_code == 200 and len(todo.json()["registros"]) == 5
    for malo in (500, 0, 201):
        assert (await client.get(_url(paciente, "/historial"), params={"limite": malo}, headers=h)).status_code == 422


async def test_historial_vacio_y_ajeno(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    vacio = await client.get(_url(paciente, "/historial"), headers=bearer(esc.recepcion))
    assert vacio.status_code == 200 and vacio.json() == {"registros": [], "siguiente_antes_de_id": None}
    assert (await client.get(_url(paciente, "/historial"), headers=bearer(esc.ana))).status_code == 403
    assert (await client.get(_url(paciente), headers=bearer(esc.ana))).status_code == 403
    assert len(await auditorias(session_factory, "lectura_odontograma")) == 1  # solo la de recepción


async def test_el_historial_trae_quien_registro(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    await client.post(_url(paciente), json=_lote(AUSENTE_36), headers=bearer(esc.admin))
    registro = (await client.get(_url(paciente, "/historial"), headers=bearer(esc.recepcion))).json()["registros"][0]
    assert registro["registrado_por"] == esc.admin_id and registro["nota"] is None


# --- 6.5 Nunca se modifica ni se borra -----------------------------------------------------------------------

def test_no_existe_ninguna_ruta_que_modifique_o_borre_el_odontograma() -> None:
    from app.main import app

    # FastAPI reciente agrupa los routers incluidos de forma diferida: el contrato público (OpenAPI) es la fuente fiable.
    rutas = [(ruta, metodo.upper()) for ruta, ops in app.openapi()["paths"].items() if "odontograma" in ruta
             for metodo in ops]
    assert rutas, "deberían existir las rutas de odontograma"
    assert {m for _, m in rutas} <= {"GET", "POST"}


async def test_los_registros_quedan_intactos_tras_nuevos_lotes(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    h = bearer(esc.recepcion)
    await client.post(_url(paciente), json=_lote(CARIES_16O), headers=h)
    async with session_factory() as s:
        antes = (await s.execute(select(OdontogramaRegistro.id, OdontogramaRegistro.estado))).all()
    await client.post(_url(paciente), json=_lote({"pieza": 16, "cara": "O", "estado": "obturado"}), headers=h)
    async with session_factory() as s:
        despues = (await s.execute(select(OdontogramaRegistro.id, OdontogramaRegistro.estado)
                                   .order_by(OdontogramaRegistro.id))).all()
    assert [tuple(f) for f in despues][:1] == [tuple(f) for f in antes] and len(despues) == 2


# --- 6.6 Ventana de O16 --------------------------------------------------------------------------------------------

async def test_con_atendido_hace_13_meses_lee_pero_no_registra(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    await turno_de(session_factory, esc, paciente, hace(dias=395))
    h = bearer(esc.ana)
    assert (await client.get(_url(paciente), headers=h)).status_code == 200
    assert (await client.get(_url(paciente, "/historial"), headers=h)).status_code == 200
    resp = await client.post(_url(paciente), json=_lote(CARIES_16O), headers=h)
    assert (resp.status_code, resp.json()["motivo"]) == (403, "acceso_clinico_vencido")
    assert await contar(session_factory, "odontograma_registro") == 0
    assert await auditorias(session_factory, "registro_odontograma") == []


async def test_con_un_confirmado_futuro_agregado_vuelve_a_poder_registrar(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    await turno_de(session_factory, esc, paciente, hace(dias=395))
    await turno_de(session_factory, esc, paciente, AHORA + timedelta(days=7), "confirmado")
    resp = await client.post(_url(paciente), json=_lote(CARIES_16O), headers=bearer(esc.ana))
    assert resp.status_code == 201
