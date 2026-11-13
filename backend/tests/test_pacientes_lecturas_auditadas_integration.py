"""C-13 (5.1, D8, O2): las lecturas de datos de pacientes dejan rastro y, sin rastro, no hay datos. Datos sintéticos (R19)."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.models.core import RegistroAuditoria
from tests.clinica_helpers import AHORA, Escenario, auditorias, crear_paciente, sembrar_escenario
from tests.conftest import bearer

LECTURAS = ("lectura_listado_pacientes", "busqueda_paciente_dni", "lectura_paciente")


@pytest.fixture
async def esc(session_factory, reloj) -> Escenario:  # type: ignore[no-untyped-def]
    reloj(AHORA)
    return await sembrar_escenario(session_factory)


@pytest.fixture
async def dos(session_factory, esc) -> dict[str, int]:  # type: ignore[no-untyped-def]
    lucia = await crear_paciente(session_factory, nombre="Lucía", apellido="Ejemplo", dni="99000001",
                                 telefono="+5491100000011")
    mateo = await crear_paciente(session_factory, nombre="Mateo", apellido="Prueba", dni="99000002",
                                 telefono="+5491100000012")
    return {"lucia": lucia, "mateo": mateo}


async def _lecturas(factory) -> list[RegistroAuditoria]:  # type: ignore[no-untyped-def]
    async with factory() as s:
        return list((await s.execute(select(RegistroAuditoria).where(RegistroAuditoria.accion.in_(LECTURAS))
                                     .order_by(RegistroAuditoria.id))).scalars())


# --- Listado ------------------------------------------------------------------------------------------------------

async def test_el_listado_con_busqueda_queda_auditado_sin_el_texto_buscado(
        session_factory, client: AsyncClient, esc, dos) -> None:  # type: ignore[no-untyped-def]
    r = await client.get("/api/panel/pacientes/listado", params={"q": "lucia", "pagina": 1},
                         headers=bearer(esc.recepcion))
    assert r.status_code == 200 and [p["apellido"] for p in r.json()["pacientes"]] == ["Ejemplo"]
    [registro] = await _lecturas(session_factory)
    assert (registro.accion, registro.usuario_id, registro.entidad, registro.entidad_id) == (
        "lectura_listado_pacientes", esc.recepcion_id, "paciente", None)
    assert registro.datos_despues["pagina"] == 1 and registro.datos_despues["con_busqueda"] is True
    assert registro.datos_despues["devueltos"] == 1
    assert "lucia" not in str(registro.datos_despues).lower() and "lucia" not in str(registro.datos_antes).lower()


async def test_un_listado_sin_busqueda_marca_con_busqueda_false_y_cuenta_lo_devuelto(
        session_factory, client: AsyncClient, esc, dos) -> None:  # type: ignore[no-untyped-def]
    r = await client.get("/api/panel/pacientes/listado", params={"orden": "ausencias", "por_pagina": 1},
                         headers=bearer(esc.admin))
    assert r.status_code == 200
    [registro] = await _lecturas(session_factory)
    assert registro.usuario_id == esc.admin_id
    assert registro.datos_despues == {"pagina": 1, "por_pagina": 1, "orden": "ausencias", "con_ausencias": False,
                                      "con_busqueda": False, "devueltos": 1}


async def test_un_listado_rechazado_no_deja_rastro(session_factory, client: AsyncClient, esc, dos) -> None:  # type: ignore[no-untyped-def]
    assert (await client.get("/api/panel/pacientes/listado", headers=bearer(esc.ana))).status_code == 403
    assert (await client.get("/api/panel/pacientes/listado", params={"q": "x"}, headers=bearer(esc.recepcion))
            ).status_code == 422
    assert (await client.get("/api/panel/pacientes/listado")).status_code == 401
    assert await _lecturas(session_factory) == []


# --- Búsqueda por DNI ---------------------------------------------------------------------------------------------

async def test_la_busqueda_por_dni_inexistente_audita_cero_encontrados_sin_dni_ni_id(
        session_factory, client: AsyncClient, esc, dos) -> None:  # type: ignore[no-untyped-def]
    r = await client.get("/api/panel/pacientes", params={"dni": "99000099"}, headers=bearer(esc.recepcion))
    assert r.status_code == 200 and r.json() == []
    [registro] = await _lecturas(session_factory)
    assert (registro.accion, registro.entidad_id, registro.datos_despues) == (
        "busqueda_paciente_dni", None, {"encontrados": 0})
    assert "99000099" not in str(registro.__dict__)


async def test_la_busqueda_por_dni_encontrada_audita_el_id_y_no_el_dni(
        session_factory, client: AsyncClient, esc, dos) -> None:  # type: ignore[no-untyped-def]
    r = await client.get("/api/panel/pacientes", params={"dni": "99000001"}, headers=bearer(esc.recepcion))
    assert r.status_code == 200 and len(r.json()) == 1
    [registro] = await _lecturas(session_factory)
    assert (registro.entidad_id, registro.datos_despues) == (str(dos["lucia"]), {"encontrados": 1})
    assert "99000001" not in str(registro.__dict__)


async def test_una_busqueda_rechazada_por_formato_o_permiso_no_deja_rastro(
        session_factory, client: AsyncClient, esc, dos) -> None:  # type: ignore[no-untyped-def]
    assert (await client.get("/api/panel/pacientes", params={"dni": "12ab"}, headers=bearer(esc.recepcion))
            ).status_code == 422
    assert (await client.get("/api/panel/pacientes", params={"dni": "99000001"}, headers=bearer(esc.ana))
            ).status_code == 403
    assert await _lecturas(session_factory) == []


# --- Datos de un paciente ------------------------------------------------------------------------------------------

async def test_la_lectura_normal_de_un_paciente_deja_su_registro(session_factory, client: AsyncClient, esc, dos) -> None:  # type: ignore[no-untyped-def]
    r = await client.get(f"/api/panel/pacientes/{dos['lucia']}", headers=bearer(esc.recepcion))
    assert r.status_code == 200 and r.json()["dni"] == "99000001"
    [registro] = await _lecturas(session_factory)
    assert (registro.accion, registro.usuario_id, registro.entidad, registro.entidad_id) == (
        "lectura_paciente", esc.recepcion_id, "paciente", str(dos["lucia"]))
    assert "99000001" not in str(registro.__dict__)


async def test_un_paciente_inexistente_o_ajeno_responde_error_sin_rastro(
        session_factory, client: AsyncClient, esc, dos) -> None:  # type: ignore[no-untyped-def]
    assert (await client.get("/api/panel/pacientes/999999", headers=bearer(esc.recepcion))).status_code == 404
    assert (await client.get(f"/api/panel/pacientes/{dos['mateo']}", headers=bearer(esc.ana))).status_code == 403
    assert await _lecturas(session_factory) == []


@pytest.mark.parametrize("ruta,parametros", [
    ("/api/panel/pacientes/listado", {"q": "lucia"}),
    ("/api/panel/pacientes", {"dni": "99000001"}),
    ("/api/panel/pacientes/{lucia}", {}),
])
async def test_si_falla_guardar_el_registro_hay_error_500_y_ningun_dato_del_paciente(
        session_factory, esc, dos, monkeypatch: pytest.MonkeyPatch, ruta: str, parametros: dict[str, str]) -> None:  # type: ignore[no-untyped-def]
    from app import pacientes
    from app.main import app

    def _falla(*args: object, **kwargs: object) -> None:
        raise RuntimeError("auditoría caída (simulada)")

    monkeypatch.setattr(pacientes.listado, "registrar", _falla, raising=False)
    monkeypatch.setattr(pacientes.service, "registrar", _falla, raising=False)
    transporte = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transporte, base_url="http://test") as c:
        r = await c.get(ruta.format(lucia=dos["lucia"]), params=parametros, headers=bearer(esc.recepcion))
    assert r.status_code == 500
    assert "Ejemplo" not in r.text and "99000001" not in r.text and "+5491100000011" not in r.text
    assert await auditorias(session_factory) == []
