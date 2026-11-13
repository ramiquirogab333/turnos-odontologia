"""C-13 (6.2, D7, O6): ``GET /api/panel/auditoria`` — filtros, keyset estable, solo admin, tipos legibles. Sintético (R19)."""

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import event, select

from app.models.core import RegistroAuditoria
from tests.clinica_helpers import Escenario, sembrar_escenario
from tests.conftest import bearer, crear_usuario_panel

URL = "/api/panel/auditoria"
AHORA = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)  # 09:00 en la clínica


@pytest.fixture
async def esc(session_factory, reloj) -> Escenario:  # type: ignore[no-untyped-def]
    reloj(AHORA)
    return await sembrar_escenario(session_factory)


async def sembrar(factory, *filas: dict[str, Any]) -> list[int]:  # type: ignore[no-untyped-def]
    """Inserta registros con instante explícito (la tabla es de solo agregado: insertar sí se puede)."""
    async with factory() as s:
        objetos = [RegistroAuditoria(**f) for f in filas]
        s.add_all(objetos)
        await s.flush()
        ids = [int(o.id) for o in objetos]
        await s.commit()
    return ids


def fila(minutos_atras: int, accion: str, entidad: str, entidad_id: str | None, usuario_id: int | None = None, *,
         origen: str | None = None, ip: str | None = "192.0.2.5", **extra: Any) -> dict[str, Any]:
    return {"created_at": AHORA - timedelta(minutes=minutos_atras), "accion": accion, "entidad": entidad,
            "entidad_id": entidad_id, "usuario_id": usuario_id, "ip": ip,
            "datos_despues": ({"origen": origen} if origen else None), **extra}


async def consultar(client: AsyncClient, token: str, **params: Any) -> Response:
    return await client.get(URL, params=params, headers=bearer(token))


async def lecturas(factory) -> list[RegistroAuditoria]:  # type: ignore[no-untyped-def]
    async with factory() as s:
        return list((await s.execute(select(RegistroAuditoria).where(RegistroAuditoria.accion == "lectura_auditoria")
                                     .order_by(RegistroAuditoria.id))).scalars())


# --- Consulta filtrada ----------------------------------------------------------------------------------------------

async def test_la_historia_de_un_turno_viene_del_mas_reciente_al_mas_antiguo_con_usuario_y_tipo(
        session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await sembrar(session_factory,
                  fila(180, "CREATE", "turno", "501", esc.recepcion_id, origen="alta_manual_panel"),
                  fila(120, "UPDATE", "turno", "501", esc.recepcion_id, origen="marcado_atendido_panel"),
                  fila(60, "UPDATE", "turno", "501", esc.admin_id, origen="deshacer_atendido_panel"),
                  fila(30, "UPDATE", "turno", "502", esc.admin_id, origen="cancelacion_panel"))
    r = await consultar(client, esc.admin, entidad="turno", entidad_id="501")
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert [i["tipo"] for i in items] == ["deshacer_atendido", "marcado_atendido", "alta_manual"]
    assert [i["usuario"]["id"] for i in items] == [esc.admin_id, esc.recepcion_id, esc.recepcion_id]
    assert items[0]["usuario"]["nombre_completo"] == "Usuario Sintético" and "email" not in items[0]["usuario"]
    assert (items[0]["accion"], items[0]["tipo_etiqueta"], items[0]["entidad"], items[0]["entidad_id"],
            items[0]["ip"]) == ("UPDATE", "Corrección de atendido", "turno", "501", "192.0.2.5")
    assert items[0]["datos_despues"] == {"origen": "deshacer_atendido_panel"}
    assert datetime.fromisoformat(items[0]["fecha_hora"]) == AHORA - timedelta(minutes=60)
    assert datetime.fromisoformat(items[0]["fecha_hora"]).tzinfo is not None
    assert r.json()["siguiente"] is None


async def test_los_filtros_por_usuario_tipo_y_rango_de_fechas_se_combinan(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await sembrar(session_factory,
                  fila(10, "cierre_caja", "cierre_caja", "1", esc.recepcion_id),
                  fila(20, "cierre_caja", "cierre_caja", "2", esc.admin_id),
                  fila(30, "anulacion_cierre_caja", "cierre_caja", "1", esc.admin_id),
                  fila(60 * 24 * 12, "cierre_caja", "cierre_caja", "0", esc.admin_id))  # hace 12 días: fuera del defecto
    r = await consultar(client, esc.admin, tipo="cierre_caja")
    assert [i["entidad_id"] for i in r.json()["items"]] == ["1", "2"]
    r = await consultar(client, esc.admin, tipo="cierre_caja", usuario_id=esc.admin_id)
    assert [i["entidad_id"] for i in r.json()["items"]] == ["2"]
    r = await consultar(client, esc.admin, desde="2026-10-20", hasta="2026-10-30")
    assert [i["entidad_id"] for i in r.json()["items"]] == ["0"]
    assert (await consultar(client, esc.admin, tipo="cierre_caja", desde="2026-10-20")).json()["items"] != []


async def test_el_dia_de_hasta_se_incluye_completo_en_hora_de_la_clinica(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    # 2026-11-09 23:30 en la clínica (UTC-3) = 2026-11-10 02:30 UTC; 2026-11-10 00:10 clínica = 03:10 UTC.
    await sembrar(session_factory,
                  {"created_at": datetime(2026, 11, 10, 2, 30, tzinfo=timezone.utc), "accion": "cierre_caja",
                   "entidad": "cierre_caja", "entidad_id": "7"},
                  {"created_at": datetime(2026, 11, 10, 3, 10, tzinfo=timezone.utc), "accion": "cierre_caja",
                   "entidad": "cierre_caja", "entidad_id": "8"})
    r = await consultar(client, esc.admin, desde="2026-11-09", hasta="2026-11-09")
    assert [i["entidad_id"] for i in r.json()["items"]] == ["7"]


async def test_un_rango_invalido_da_422_y_ningun_registro(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await sembrar(session_factory, fila(10, "cierre_caja", "cierre_caja", "1"))
    for params in ({"desde": "2026-11-10", "hasta": "2026-11-09"}, {"desde": "2025-10-01", "hasta": "2026-11-10"},
                   {"desde": "2026-12-01"}, {"cursor": "no-es-un-cursor"}, {"por_pagina": 101}):
        r = await consultar(client, esc.admin, **params)
        assert r.status_code == 422, params
        assert "items" not in r.json()
    assert await lecturas(session_factory) == []


async def test_la_paginacion_keyset_es_estable_aunque_entren_registros_nuevos_entre_paginas(
        session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    ids = await sembrar(session_factory, *(fila(i + 1, "cierre_caja", "cierre_caja", str(i)) for i in range(120)))
    esperado = [i for _, i in sorted(((AHORA - timedelta(minutes=k + 1), ids[k]) for k in range(120)), reverse=True)]
    p1 = (await consultar(client, esc.admin, tipo="cierre_caja")).json()
    assert [i["id"] for i in p1["items"]] == esperado[:50] and p1["siguiente"]
    await sembrar(session_factory, *(fila(0, "cierre_caja", "cierre_caja", f"nuevo{n}") for n in range(3)))
    p2 = (await consultar(client, esc.admin, tipo="cierre_caja", cursor=p1["siguiente"])).json()
    assert [i["id"] for i in p2["items"]] == esperado[50:100] and p2["siguiente"]
    p3 = (await consultar(client, esc.admin, tipo="cierre_caja", cursor=p2["siguiente"])).json()
    assert [i["id"] for i in p3["items"]] == esperado[100:] and p3["siguiente"] is None


async def test_registros_con_el_mismo_instante_se_desempatan_por_id_sin_repetir(
        session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    ids = await sembrar(session_factory, *(fila(5, "cierre_caja", "cierre_caja", str(i)) for i in range(5)))
    vistos: list[int] = []
    cursor: str | None = None
    for _ in range(5):
        params: dict[str, Any] = {"tipo": "cierre_caja", "por_pagina": 2}
        if cursor:
            params["cursor"] = cursor
        pagina = (await consultar(client, esc.admin, **params)).json()
        vistos += [i["id"] for i in pagina["items"]]
        cursor = pagina["siguiente"]
        if cursor is None:
            break
    assert vistos == sorted(ids, reverse=True)


# --- Solo el admin --------------------------------------------------------------------------------------------------

async def test_el_admin_consulta_y_queda_un_registro_lectura_auditoria_con_sus_filtros(
        session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    r = await consultar(client, esc.admin, entidad="turno", tipo="alta_manual", usuario_id=esc.recepcion_id)
    assert r.status_code == 200 and r.json() == {"items": [], "siguiente": None}
    [lectura] = await lecturas(session_factory)
    assert (lectura.usuario_id, lectura.entidad, lectura.entidad_id) == (esc.admin_id, "auditoria", None)
    assert lectura.datos_despues == {"desde": "2026-11-04", "hasta": "2026-11-10", "por_pagina": 50,
                                     "con_cursor": False, "entidad": "turno", "usuario_id": esc.recepcion_id,
                                     "tipo": "alta_manual"}


async def test_recepcion_y_odontologa_reciben_403_sin_registros_ni_lectura(
        session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await sembrar(session_factory, fila(10, "cierre_caja", "cierre_caja", "1"))
    for token in (esc.recepcion, esc.ana):
        r = await consultar(client, token)
        assert r.status_code == 403 and "items" not in r.json()
    assert (await client.get(URL)).status_code == 401
    assert await lecturas(session_factory) == []


async def test_un_usuario_con_roles_recepcion_y_admin_consulta(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    _, token = await crear_usuario_panel(session_factory, "doble.rol@turnos.test", ["recepcion", "admin"])
    assert (await consultar(client, token)).status_code == 200


# --- Tipos legibles -------------------------------------------------------------------------------------------------

async def test_las_seis_acciones_de_c12_traen_su_tipo(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await sembrar(session_factory,
                  fila(60, "cierre_caja", "cierre_caja", "1"), fila(50, "anulacion_cierre_caja", "cierre_caja", "1"),
                  fila(40, "devolucion_sena_registrada", "pago_sena", "9"),
                  fila(30, "devolucion_excedente_registrada", "pago_sena_aprobacion", "3"),
                  fila(20, "sena_revision_rechazada", "pago_sena", "9"),
                  fila(10, "UPDATE", "turno", "5", origen="deshacer_atendido_panel"))
    items = (await consultar(client, esc.admin)).json()["items"]
    assert [i["tipo"] for i in items] == ["deshacer_atendido", "rechazo_revision_sena", "devolucion_excedente",
                                          "devolucion_sena", "anulacion_cierre_caja", "cierre_caja"]


async def test_filtrar_por_un_tipo_inexistente_da_422_con_la_lista_de_tipos_validos(
        session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    r = await consultar(client, esc.admin, tipo="inventado")
    assert r.status_code == 422 and "cierre_caja" in r.text and "deshacer_atendido" in r.text
    assert await lecturas(session_factory) == []


async def test_un_historico_sin_tipo_conocido_es_otro_con_su_accion_y_la_fila_no_cambia(
        session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    [rid] = await sembrar(session_factory, fila(10, "UPDATE", "configuracion_sena", "1", datos_antes={"a": 1}))
    item = (await consultar(client, esc.admin, tipo="otro")).json()["items"][0]
    assert (item["tipo"], item["tipo_etiqueta"], item["accion"]) == ("otro", "UPDATE", "UPDATE")
    async with session_factory() as s:
        guardado = (await s.execute(select(RegistroAuditoria).where(RegistroAuditoria.id == rid))).scalar_one()
    assert (guardado.accion, guardado.entidad, guardado.datos_antes) == ("UPDATE", "configuracion_sena", {"a": 1})
    assert (await consultar(client, esc.admin, tipo="cierre_caja")).json()["items"] == []  # otro no se cuela en otros


async def test_un_registro_sin_usuario_trae_usuario_nulo(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await sembrar(session_factory, fila(10, "CREATE", "turno", "7", None, origen="reserva_publica", ip=None))
    [item] = (await consultar(client, esc.admin, tipo="reserva_publica")).json()["items"]
    assert (item["usuario"], item["ip"], item["tipo"]) == (None, None, "reserva_publica")


async def test_la_consulta_usa_un_unico_select_con_join_a_usuario(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await sembrar(session_factory, *(fila(i + 1, "cierre_caja", "cierre_caja", str(i), esc.recepcion_id) for i in range(20)))
    from app.shared.db import get_engine

    sentencias: list[str] = []

    def contar(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        sentencias.append(statement)

    motor = get_engine().sync_engine
    event.listen(motor, "before_cursor_execute", contar)
    try:
        r = await consultar(client, esc.admin, tipo="cierre_caja")
    finally:
        event.remove(motor, "before_cursor_execute", contar)
    assert r.status_code == 200 and len(r.json()["items"]) == 20
    # La verificación de sesión (C-15) no cuenta: queda la página, con su JOIN a usuario.
    selects = [s for s in sentencias if s.lstrip().upper().startswith("SELECT") and "sesion_panel" not in s]
    assert len(selects) == 1 and "JOIN usuario" in selects[0], selects
