"""C-12 (grupo 7): listado de pacientes con búsqueda libre y ausentismo por paciente. Datos sintéticos (R19)."""

import logging
from datetime import datetime
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import event, select

from app.models.core import RegistroAuditoria
from tests.clinica_helpers import (
    AHORA, Escenario, crear_obra_social, crear_paciente, hace, sembrar_escenario, turno_de,
)
from tests.conftest import bearer, crear_usuario_panel

URL = "/api/panel/pacientes/listado"


@pytest.fixture
async def esc(session_factory, reloj) -> Escenario:  # type: ignore[no-untyped-def]
    reloj(AHORA)
    return await sembrar_escenario(session_factory)


@pytest.fixture
async def dos(session_factory, esc) -> dict[str, int]:  # type: ignore[no-untyped-def]
    os_id = await crear_obra_social(session_factory, "SINT", "Obra Social Sintética")
    lucia = await crear_paciente(session_factory, nombre="Lucía", apellido="Ejemplo", dni="99000001",
                                 telefono="+5491100000011", obra_social_id=os_id)
    mateo = await crear_paciente(session_factory, nombre="Mateo", apellido="Prueba", dni="99000002",
                                 telefono="+5491100000012")
    return {"lucia": lucia, "mateo": mateo, "os": os_id}


async def listar(client: AsyncClient, token: str, **params: Any) -> Response:
    return await client.get(URL, params=params, headers=bearer(token))


def nombres(r: Response) -> list[str]:
    return [f"{p['nombre']} {p['apellido']}" for p in r.json()["pacientes"]]


# --- 7.1 Búsqueda libre --------------------------------------------------------------------------------------------

async def test_buscar_lucia_sin_acento_ni_mayusculas_trae_a_lucia_con_sus_datos_y_total_1(client: AsyncClient, esc, dos) -> None:  # type: ignore[no-untyped-def]
    for q in ("lucia", "LUCÍA", "lucía", "  Lucia  "):
        r = await listar(client, esc.recepcion, q=q)
        assert r.status_code == 200, r.text
        assert r.json()["total"] == 1 and nombres(r) == ["Lucía Ejemplo"], q
    [p] = r.json()["pacientes"]
    assert (p["id"], p["dni"], p["telefono"], p["obra_social"]) == (
        dos["lucia"], "99000001", "+5491100000011", {"id": dos["os"], "nombre": "Obra Social Sintética"})
    assert (r.json()["pagina"], r.json()["por_pagina"]) == (1, 20)


async def test_la_odontologa_recibe_403_y_una_busqueda_de_un_caracter_422_sin_datos(client: AsyncClient, esc, dos) -> None:  # type: ignore[no-untyped-def]
    r = await listar(client, esc.ana)
    assert r.status_code == 403 and "Ejemplo" not in r.text and "99000001" not in r.text
    assert (await client.get(URL)).status_code == 401
    corta = await listar(client, esc.recepcion, q="l")
    assert corta.status_code == 422 and "Ejemplo" not in corta.text and "99000001" not in corta.text
    assert (await listar(client, esc.recepcion, q="x" * 61)).status_code == 422


async def test_comienzo_del_dni_apellido_y_nombre_y_pagina_fuera_de_rango(client: AsyncClient, esc, dos) -> None:  # type: ignore[no-untyped-def]
    assert nombres(await listar(client, esc.recepcion, q="9900000")) == ["Lucía Ejemplo", "Mateo Prueba"]
    assert nombres(await listar(client, esc.recepcion, q="ejemplo lu")) == ["Lucía Ejemplo"]
    assert nombres(await listar(client, esc.recepcion, q="Lucia   Ejemplo")) == ["Lucía Ejemplo"]  # espacios simples
    vacia = await listar(client, esc.recepcion, pagina=5)
    assert vacia.json()["pacientes"] == [] and vacia.json()["total"] == 2


async def test_el_dni_se_busca_por_comienzo_y_no_por_cualquier_parte(client: AsyncClient, esc, dos) -> None:  # type: ignore[no-untyped-def]
    assert nombres(await listar(client, esc.recepcion, q="990000")) == ["Lucía Ejemplo", "Mateo Prueba"]
    assert (await listar(client, esc.recepcion, q="0001")).json()["total"] == 0  # "99000001" no empieza con 0001
    assert nombres(await listar(client, esc.recepcion, q="99000002")) == ["Mateo Prueba"]


@pytest.mark.parametrize("q", ["%%", "__", "\\\\", "%a", "a%"])
async def test_los_comodines_de_la_busqueda_se_escapan_y_no_traen_a_todos(client: AsyncClient, esc, dos, q: str) -> None:  # type: ignore[no-untyped-def]
    r = await listar(client, esc.recepcion, q=q)
    assert r.status_code == 200 and r.json()["total"] == 0 and r.json()["pacientes"] == []


async def test_orden_por_apellido_y_nombre_paginacion_y_limites(session_factory, client: AsyncClient, esc, dos) -> None:  # type: ignore[no-untyped-def]
    await crear_paciente(session_factory, nombre="Zoe", apellido="Ejemplo", dni="99000003")
    await crear_paciente(session_factory, nombre="Ana", apellido="Ejemplo", dni="99000004")
    assert nombres(await listar(client, esc.recepcion)) == ["Ana Ejemplo", "Lucía Ejemplo", "Zoe Ejemplo", "Mateo Prueba"]
    segunda = await listar(client, esc.recepcion, pagina=2, por_pagina=3)
    assert nombres(segunda) == ["Mateo Prueba"] and segunda.json()["total"] == 4
    for malo in ({"pagina": 0}, {"por_pagina": 0}, {"por_pagina": 51}):
        assert (await listar(client, esc.recepcion, **malo)).status_code == 422
    assert (await listar(client, esc.recepcion, por_pagina=50)).status_code == 200


async def test_admin_y_un_usuario_con_dos_roles_tambien_listan(session_factory, client: AsyncClient, esc, dos) -> None:  # type: ignore[no-untyped-def]
    assert (await listar(client, esc.admin)).status_code == 200
    _, doble = await crear_usuario_panel(session_factory, "doble@turnos.test", ["odontologo", "recepcion"])
    assert (await listar(client, doble)).status_code == 200


async def test_el_listado_nuevo_no_rompe_la_busqueda_por_dni_ni_la_consulta_por_id(client: AsyncClient, esc, dos) -> None:  # type: ignore[no-untyped-def]
    assert (await client.get("/api/panel/pacientes", params={"dni": "99000001"}, headers=bearer(esc.recepcion))).json()[0]["id"] == dos["lucia"]
    assert (await client.get(f"/api/panel/pacientes/{dos['mateo']}", headers=bearer(esc.recepcion))).status_code == 200


# --- 7.3 Ausentismo por paciente --------------------------------------------------------------------------------

async def test_un_paciente_con_dos_atendidos_y_un_ausente_lo_informa_y_el_filtro_deja_solo_a_quien_falto(session_factory, client: AsyncClient, esc, dos) -> None:  # type: ignore[no-untyped-def]
    await turno_de(session_factory, esc, dos["mateo"], hace(dias=30), "atendido")
    await turno_de(session_factory, esc, dos["mateo"], hace(dias=20), "atendido")
    ultimo = await turno_de(session_factory, esc, dos["mateo"], hace(dias=10), "ausente")
    await turno_de(session_factory, esc, dos["lucia"], hace(dias=5), "atendido")
    r = await listar(client, esc.recepcion, con_ausencias="true")
    [p] = r.json()["pacientes"]
    assert (p["nombre"], p["atendidos"], p["ausentes"]) == ("Mateo", 2, 1)
    assert datetime.fromisoformat(p["ultimo_turno"]) == hace(dias=10) and ultimo
    assert r.json()["total"] == 1
    todos = {x["nombre"]: (x["atendidos"], x["ausentes"]) for x in (await listar(client, esc.recepcion)).json()["pacientes"]}
    assert todos == {"Lucía": (1, 0), "Mateo": (2, 1)}


async def test_orden_por_ausencias_va_de_mas_a_menos_y_un_valor_invalido_da_422(session_factory, client: AsyncClient, esc, dos) -> None:  # type: ignore[no-untyped-def]
    tercero = await crear_paciente(session_factory, nombre="Ana", apellido="Zeta", dni="99000003")
    for dias in (10, 9):
        await turno_de(session_factory, esc, dos["mateo"], hace(dias=dias), "ausente")
    await turno_de(session_factory, esc, tercero, hace(dias=8), "ausente")
    r = await listar(client, esc.recepcion, orden="ausencias")
    assert [(p["nombre"], p["ausentes"]) for p in r.json()["pacientes"]] == [("Mateo", 2), ("Ana", 1), ("Lucía", 0)]
    assert (await listar(client, esc.recepcion, orden="telefono")).status_code == 422
    assert [p["nombre"] for p in (await listar(client, esc.recepcion, orden="apellido")).json()["pacientes"]] == ["Lucía", "Mateo", "Ana"]


async def test_un_ausente_sin_vincular_una_pre_reserva_y_un_cancelado_no_cuentan_para_nadie(session_factory, client: AsyncClient, esc, dos) -> None:  # type: ignore[no-untyped-def]
    await turno_de(session_factory, esc, dos["lucia"], hace(dias=5), "en_espera", vence=hace(dias=1))
    await turno_de(session_factory, esc, dos["lucia"], hace(dias=4), "cancelado")
    await turno_de(session_factory, esc, None, hace(dias=3), "ausente")  # a su nombre, pero nadie lo vinculó
    r = await listar(client, esc.recepcion, q="lucia")
    [p] = r.json()["pacientes"]
    assert (p["atendidos"], p["ausentes"], p["ultimo_turno"]) == (0, 0, None)
    assert (await listar(client, esc.recepcion, q="lucia", con_ausencias="true")).json()["total"] == 0


# --- 7.4 Sin N+1 y sin guardar el texto buscado --------------------------------------------------------------------

async def test_la_consulta_hace_dos_sentencias_para_20_pacientes_con_turnos(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    for i in range(20):
        p = await crear_paciente(session_factory, nombre=f"Paciente{i:02d}", apellido="Sintético", dni=f"9910{i:04d}")
        await turno_de(session_factory, esc, p, hace(dias=40 + i), "atendido")
        await turno_de(session_factory, esc, p, hace(dias=1 + i), "ausente", prof="bruno")
    from app.shared.db import get_engine

    sentencias: list[str] = []

    def contar(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        sentencias.append(statement)

    motor = get_engine().sync_engine
    event.listen(motor, "before_cursor_execute", contar)
    try:
        r = await listar(client, esc.recepcion)
    finally:
        event.remove(motor, "before_cursor_execute", contar)
    assert r.status_code == 200 and len(r.json()["pacientes"]) == 20 and r.json()["total"] == 20
    assert all(p["atendidos"] == 1 and p["ausentes"] == 1 for p in r.json()["pacientes"])
    # La verificación de sesión del pedido (C-15, una sola consulta a sesion_panel) no cuenta: son la página y el total.
    consultas = [s for s in sentencias if s.lstrip().upper().startswith("SELECT") and "sesion_panel" not in s]
    assert len(consultas) == 2, consultas  # la página y el total


async def test_el_texto_buscado_no_se_guarda_en_la_auditoria_ni_en_los_logs(session_factory, client: AsyncClient, esc, dos, caplog) -> None:  # type: ignore[no-untyped-def]
    with caplog.at_level(logging.DEBUG):
        r = await listar(client, esc.recepcion, q="secreto-sintetico")
        assert r.status_code == 200
        await listar(client, esc.recepcion, q="Lucia")
    # (el cliente httpx del test loguea su propia URL; lo que importa son los logs de la aplicación y sus librerías)
    del_servidor = [r for r in caplog.records if not r.name.startswith("httpx")]
    assert all("secreto-sintetico" not in r.getMessage() and "Lucia" not in r.getMessage() for r in del_servidor)
    async with session_factory() as s:
        registros = (await s.execute(select(RegistroAuditoria))).scalars().all()
    assert all("secreto-sintetico" not in str(x.datos_despues) and "Lucia" not in str(x.datos_despues)
               for x in registros)
