"""C-08 (4.1): GET /api/panel/agenda y /opciones. PostgreSQL real. Datos 100 % sintéticos (R19)."""

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import event
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.db import get_engine
from tests.conftest import bearer, crear_usuario_panel
from tests.panel_helpers import (
    BA, LUNES, TELEFONO, insertar_pago, insertar_turno, local, sembrar_mundo,
)

URL = "/api/panel/agenda"
MARTES = LUNES + timedelta(days=1)
DOMINGO = LUNES + timedelta(days=6)


@pytest.fixture
async def mundo(session_factory, clean_db):
    return await sembrar_mundo(session_factory)


@pytest.fixture
async def rec(session_factory, mundo) -> dict[str, str]:
    return bearer((await crear_usuario_panel(session_factory, "recepcion@turnos.test", ["recepcion"]))[1])


@pytest.fixture
async def dra(session_factory, mundo) -> dict[str, str]:
    return bearer((await crear_usuario_panel(session_factory, "dra.ficticia@turnos.test", ["odontologo"],
                                             profesional_id=mundo["ana"]))[1])


async def _dia(client, cab, dia: date, **params):
    return await client.get(URL, params={"vista": "dia", "fecha": dia.isoformat(), **params}, headers=cab)


def _ids(r) -> list[int]:
    return [t["id"] for t in r.json()["turnos"]]


# --- vista día y semana ------------------------------------------------------------------------------------

async def test_agenda_del_dia_ordenada_con_inicio_en_hora_de_la_clinica(client, rec, mundo, session_factory, reloj) -> None:
    reloj(local(LUNES, "07:00"))
    segundo = await insertar_turno(session_factory, mundo, local(MARTES, "09:30"), estado="confirmado",
                                   nombre="Lucía Ejemplo", sillon="s2")
    primero = await insertar_turno(session_factory, mundo, local(MARTES, "09:00"))
    await insertar_turno(session_factory, mundo, local(LUNES, "09:00"))  # otro día
    r = await _dia(client, rec, MARTES)
    assert r.status_code == 200, r.text
    assert _ids(r) == [primero, segundo]
    t = r.json()["turnos"][0]
    assert t["inicio"] == "2031-11-18T09:00:00-03:00" and t["fin"] == "2031-11-18T09:30:00-03:00"
    assert (t["estado"], t["origen"], t["paciente_nombre"]) == ("reservado", "web", "Carlos Sintético")
    assert t["profesional"]["nombre"] == "Dra. Ana Ficticia" and t["sillon"]["nombre"] == "Sillón 1"
    assert t["tratamiento"]["nombre"] == "Limpieza dental"


async def test_agenda_de_la_semana_va_de_lunes_a_domingo(client, rec, mundo, session_factory, reloj) -> None:
    reloj(local(LUNES, "07:00"))
    lunes = await insertar_turno(session_factory, mundo, local(LUNES, "09:00"))
    domingo = await insertar_turno(session_factory, mundo, local(DOMINGO, "11:00"))
    await insertar_turno(session_factory, mundo, local(LUNES - timedelta(days=1), "11:00"))  # domingo anterior
    r = await client.get(URL, params={"vista": "semana", "fecha": (LUNES + timedelta(days=2)).isoformat()}, headers=rec)
    assert r.status_code == 200
    assert _ids(r) == [lunes, domingo]
    assert (r.json()["desde"], r.json()["hasta"]) == (LUNES.isoformat(), DOMINGO.isoformat())


async def test_limite_de_la_semana_en_hora_de_la_clinica_domingo_2330_si_y_lunes_0000_no(
        client, rec, mundo, session_factory, reloj) -> None:
    reloj(local(LUNES, "07:00"))
    domingo_2330 = await insertar_turno(session_factory, mundo, local(DOMINGO, "23:30"))  # en UTC ya es lunes
    await insertar_turno(session_factory, mundo, local(DOMINGO + timedelta(days=1), "00:00"), sillon="s2")
    r = await client.get(URL, params={"vista": "semana", "fecha": DOMINGO.isoformat()}, headers=rec)
    assert _ids(r) == [domingo_2330]


async def test_limite_del_dia_la_medianoche_local_pertenece_al_dia_que_empieza(
        client, rec, mundo, session_factory, reloj) -> None:
    reloj(local(LUNES, "07:00"))
    tarde = await insertar_turno(session_factory, mundo, local(LUNES, "23:30"))
    medianoche = await insertar_turno(session_factory, mundo, local(MARTES, "00:00"), sillon="s2")
    assert _ids(await _dia(client, rec, LUNES)) == [tarde]
    assert _ids(await _dia(client, rec, MARTES)) == [medianoche]


@pytest.mark.parametrize("params", [
    {"vista": "mes", "fecha": "2031-11-17"}, {"vista": "dia", "fecha": "17-11-2031"},
    {"vista": "dia"}, {"fecha": "2031-11-17"}, {"vista": "dia", "fecha": "2031-11-17", "foo": "x"},
])
async def test_parametros_invalidos_son_422(client, rec, params) -> None:
    assert (await client.get(URL, params=params, headers=rec)).status_code == 422


# --- roles ------------------------------------------------------------------------------------------------

async def test_la_odontologa_ve_solo_su_agenda(client, dra, mundo, session_factory, reloj) -> None:
    reloj(local(LUNES, "07:00"))
    suyo = await insertar_turno(session_factory, mundo, local(MARTES, "09:00"))
    await insertar_turno(session_factory, mundo, local(MARTES, "09:00"), prof="bruno", sillon="s2")
    assert _ids(await _dia(client, dra, MARTES)) == [suyo]


async def test_la_odontologa_pidiendo_otra_agenda_es_403_y_sin_token_es_401(client, dra, mundo, session_factory) -> None:
    await insertar_turno(session_factory, mundo, local(MARTES, "09:00"), prof="bruno", sillon="s2")
    r = await _dia(client, dra, MARTES, profesional_id=mundo["bruno"])
    assert r.status_code == 403 and "turnos" not in r.json()
    assert (await client.get(URL, params={"vista": "dia", "fecha": MARTES.isoformat()})).status_code == 401
    suya = await _dia(client, dra, MARTES, profesional_id=mundo["ana"])
    assert suya.status_code == 200


async def test_odontologo_sin_profesional_asociado_es_403_con_motivo(client, mundo, session_factory) -> None:
    _, token = await crear_usuario_panel(session_factory, "huerfano@turnos.test", ["odontologo"])
    r = await _dia(client, bearer(token), MARTES)
    assert r.status_code == 403
    assert r.json()["motivo"] == "sin_profesional_asociado" and "clínica" in r.json()["detail"]


async def test_recepcion_y_un_usuario_con_dos_roles_ven_todas_las_agendas(client, rec, mundo, session_factory, reloj) -> None:
    reloj(local(LUNES, "07:00"))
    a = await insertar_turno(session_factory, mundo, local(MARTES, "09:00"))
    b = await insertar_turno(session_factory, mundo, local(MARTES, "09:00"), prof="bruno", sillon="s2")
    assert sorted(_ids(await _dia(client, rec, MARTES))) == sorted([a, b])
    _, token = await crear_usuario_panel(session_factory, "doble@turnos.test", ["odontologo", "recepcion"],
                                         profesional_id=mundo["ana"])
    assert sorted(_ids(await _dia(client, bearer(token), MARTES))) == sorted([a, b])
    _, admin = await crear_usuario_panel(session_factory, "admin@turnos.test", ["admin"])
    assert sorted(_ids(await _dia(client, bearer(admin), MARTES))) == sorted([a, b])


async def test_un_usuario_sin_roles_del_panel_es_403(client, mundo, session_factory) -> None:
    _, token = await crear_usuario_panel(session_factory, "sinrol@turnos.test", [])
    assert (await _dia(client, bearer(token), MARTES)).status_code == 403


# --- pre-reservas, cancelados y atendidos -----------------------------------------------------------------

async def test_en_espera_vigente_no_bloquea_atendido_si_y_vencida_y_cancelado_no_aparecen(
        client, rec, mundo, session_factory, reloj) -> None:
    ahora = local(LUNES, "07:00")
    reloj(ahora)
    vigente = await insertar_turno(session_factory, mundo, local(MARTES, "10:00"), estado="en_espera",
                                   vence=ahora + timedelta(minutes=30), sillon="s2")
    await insertar_turno(session_factory, mundo, local(MARTES, "10:00"), estado="en_espera",
                         vence=ahora - timedelta(seconds=1), prof="bruno")  # vencida y sin barrer
    await insertar_turno(session_factory, mundo, local(MARTES, "11:00"), estado="cancelado")
    reservado = await insertar_turno(session_factory, mundo, local(MARTES, "10:00"))
    atendido = await insertar_turno(session_factory, mundo, local(MARTES, "12:00"), estado="atendido")
    confirmado = await insertar_turno(session_factory, mundo, local(MARTES, "12:30"), estado="confirmado")
    r = await _dia(client, rec, MARTES)
    por_id = {t["id"]: t for t in r.json()["turnos"]}
    assert set(por_id) == {vigente, reservado, atendido, confirmado}
    assert por_id[vigente]["bloquea_agenda"] is False and por_id[vigente]["estado"] == "en_espera"
    assert all(por_id[i]["bloquea_agenda"] is True for i in (reservado, atendido, confirmado))


async def test_la_pre_reserva_que_vence_justo_ahora_ya_no_se_muestra(client, rec, mundo, session_factory, reloj) -> None:
    ahora = local(LUNES, "07:00")
    reloj(ahora)
    await insertar_turno(session_factory, mundo, local(MARTES, "10:00"), estado="en_espera", vence=ahora)
    assert _ids(await _dia(client, rec, MARTES)) == []


async def test_los_turnos_bloqueantes_de_una_misma_profesional_o_sillon_no_se_superponen(
        client, rec, mundo, session_factory, reloj) -> None:
    reloj(local(LUNES, "07:00"))
    await insertar_turno(session_factory, mundo, local(MARTES, "10:00"))
    await insertar_turno(session_factory, mundo, local(MARTES, "10:30"))  # contiguo: no se pisan
    await insertar_turno(session_factory, mundo, local(MARTES, "10:15"), prof="bruno", sillon="s2")
    turnos = [t for t in (await _dia(client, rec, MARTES)).json()["turnos"] if t["bloquea_agenda"]]
    assert len(turnos) == 3
    for i, a in enumerate(turnos):
        for b in turnos[i + 1:]:
            if a["profesional"]["id"] == b["profesional"]["id"] or a["sillon"]["id"] == b["sillon"]["id"]:
                assert a["fin"] <= b["inicio"] or b["fin"] <= a["inicio"]


async def test_la_base_rechaza_un_solape_bloqueante(session_factory, mundo) -> None:
    await insertar_turno(session_factory, mundo, local(MARTES, "10:00"))
    with pytest.raises(DBAPIError) as exc:
        await insertar_turno(session_factory, mundo, local(MARTES, "10:15"), sillon="s2")
    assert getattr(exc.value.orig, "sqlstate", "") == "23P01"


# --- filtros y opciones -----------------------------------------------------------------------------------

async def test_filtros_por_sillon_por_profesional_y_combinados(client, rec, mundo, session_factory, reloj) -> None:
    reloj(local(LUNES, "07:00"))
    en_s1 = await insertar_turno(session_factory, mundo, local(MARTES, "09:00"))
    en_s2 = await insertar_turno(session_factory, mundo, local(MARTES, "09:00"), prof="bruno", sillon="s2")
    assert _ids(await _dia(client, rec, MARTES, sillon_id=mundo["s2"])) == [en_s2]
    assert _ids(await _dia(client, rec, MARTES, profesional_id=mundo["ana"])) == [en_s1]
    combinado = await _dia(client, rec, MARTES, profesional_id=mundo["ana"], sillon_id=mundo["s2"])
    assert combinado.status_code == 200 and combinado.json()["turnos"] == []


@pytest.mark.parametrize("filtro", ["sillon_id", "profesional_id"])
async def test_filtro_por_un_id_inexistente_es_422_sin_turnos(client, rec, mundo, filtro) -> None:
    r = await _dia(client, rec, MARTES, **{filtro: 999999})
    assert r.status_code == 422 and "turnos" not in r.json()


# --- contacto ---------------------------------------------------------------------------------------------

async def test_el_telefono_es_para_recepcion_y_nulo_para_la_odontologa_y_nunca_hay_codigo_de_gestion(
        client, rec, dra, mundo, session_factory, reloj) -> None:
    reloj(local(LUNES, "07:00"))
    await insertar_turno(session_factory, mundo, local(MARTES, "09:00"))
    de_recepcion = await _dia(client, rec, MARTES)
    de_la_dra = await _dia(client, dra, MARTES)
    assert de_recepcion.json()["turnos"][0]["paciente_telefono"] == TELEFONO
    t = de_la_dra.json()["turnos"][0]
    assert t["paciente_telefono"] is None and t["paciente_nombre"] == "Carlos Sintético"
    for r in (de_recepcion, de_la_dra):
        assert "codigo_gestion" not in r.text


async def test_un_turno_sin_contacto_trae_nombre_y_telefono_nulos(client, rec, mundo, session_factory, reloj) -> None:
    reloj(local(LUNES, "07:00"))
    await insertar_turno(session_factory, mundo, local(MARTES, "09:00"), nombre=None, telefono=None, con_codigo=False)
    t = (await _dia(client, rec, MARTES)).json()["turnos"][0]
    assert t["paciente_nombre"] is None and t["paciente_telefono"] is None


# --- seña y acciones --------------------------------------------------------------------------------------

async def test_turno_con_sena_acreditada_a_menos_de_24_horas_no_tiene_acciones(
        client, rec, mundo, session_factory, reloj) -> None:
    reloj(local(MARTES - timedelta(days=1), "20:00"))
    tid = await insertar_turno(session_factory, mundo, local(MARTES, "09:00"))
    await insertar_pago(session_factory, tid, "acreditado", monto="3000.00")
    t = (await _dia(client, rec, MARTES)).json()["turnos"][0]
    assert t["inicio"] == "2031-11-18T09:00:00-03:00"
    assert t["sena"] == {"estado": "acreditado", "monto": "3000.00"} and t["acciones"] == []


async def test_el_estado_de_la_sena_es_el_del_ultimo_pago(client, rec, mundo, session_factory, reloj) -> None:
    reloj(local(LUNES, "07:00"))
    tid = await insertar_turno(session_factory, mundo, local(MARTES, "09:00"))
    await insertar_pago(session_factory, tid, "vencido", monto="1000.00")
    await insertar_pago(session_factory, tid, "acreditado", monto="3000.00")
    t = (await _dia(client, rec, MARTES)).json()["turnos"][0]
    assert t["sena"] == {"estado": "acreditado", "monto": "3000.00"}


async def test_acciones_de_un_turno_manual_sin_sena_segun_el_momento(client, rec, mundo, session_factory, reloj) -> None:
    await insertar_turno(session_factory, mundo, local(MARTES, "09:00"), origen="manual")
    esperado = [
        (local(MARTES, "08:00"), ["atendido"]),
        (local(MARTES, "09:09") + timedelta(seconds=59), ["atendido"]),
        (local(MARTES, "09:10"), ["atendido", "ausente"]),
    ]
    for ahora, acciones in esperado:
        reloj(ahora)
        t = (await _dia(client, rec, MARTES)).json()["turnos"][0]
        assert (t["sena"], t["origen"], t["acciones"]) == (None, "manual", acciones), ahora


async def test_la_odontologa_no_recibe_acciones_aunque_el_turno_haya_empezado(client, dra, mundo, session_factory, reloj) -> None:
    reloj(local(MARTES, "09:20"))
    await insertar_turno(session_factory, mundo, local(MARTES, "09:00"))
    assert (await _dia(client, dra, MARTES)).json()["turnos"][0]["acciones"] == []


async def test_en_espera_ofrece_cancelar(client, rec, mundo, session_factory, reloj) -> None:
    ahora = local(LUNES, "07:00")
    reloj(ahora)
    await insertar_turno(session_factory, mundo, local(MARTES, "10:00"), estado="en_espera",
                         vence=ahora + timedelta(minutes=30))
    t = (await _dia(client, rec, MARTES)).json()["turnos"][0]
    assert t["acciones"] == ["cancelar"] and t["vence_en"] is not None


# --- sin N+1 ----------------------------------------------------------------------------------------------

async def _consultas(client, cab, dia: date) -> int:
    sentencias: list[str] = []

    def contar(conn, cursor, statement, parameters, context, executemany) -> None:  # noqa: ANN001
        sentencias.append(statement)

    motor = get_engine().sync_engine
    event.listen(motor, "before_cursor_execute", contar)
    try:
        r = await _dia(client, cab, dia)
        assert r.status_code == 200
    finally:
        event.remove(motor, "before_cursor_execute", contar)
    return len(sentencias)


async def test_el_numero_de_consultas_no_crece_con_la_cantidad_de_turnos(client, rec, mundo, session_factory, reloj) -> None:
    reloj(local(LUNES, "07:00"))
    una = await insertar_turno(session_factory, mundo, local(MARTES, "09:00"))
    await insertar_pago(session_factory, una, "acreditado")
    con_uno = await _consultas(client, rec, MARTES)
    for i in range(1, 8):
        tid = await insertar_turno(session_factory, mundo, local(MARTES, "09:00") + timedelta(minutes=30 * i),
                                   prof="bruno" if i % 2 else "ana", sillon="s2" if i % 2 else "s1")
        await insertar_pago(session_factory, tid, "acreditado")
    assert await _consultas(client, rec, MARTES) == con_uno


# --- /opciones --------------------------------------------------------------------------------------------

async def test_opciones_para_recepcion_trae_todo_y_para_la_odontologa_solo_su_profesional(
        client, rec, dra, mundo, session_factory) -> None:
    from app.turnos.models import Sillon

    async with session_factory() as s:
        s.add(Sillon(nombre="Sillón 3", estado="inactivo"))
        await s.commit()
    todo = await client.get(URL + "/opciones", headers=rec)
    assert todo.status_code == 200
    j = todo.json()
    assert sorted(p["nombre"] for p in j["profesionales"]) == ["Dr. Bruno Ejemplo", "Dra. Ana Ficticia"]
    assert sorted(x["nombre"] for x in j["sillones"]) == ["Sillón 1", "Sillón 2"]  # solo activos
    assert [t["nombre"] for t in j["tratamientos"]] == ["Limpieza dental"] and j["tratamientos"][0]["duracion_minutos"] == 30
    propio = (await client.get(URL + "/opciones", headers=dra)).json()
    assert [p["id"] for p in propio["profesionales"]] == [mundo["ana"]]
    assert j["puede_escribir"] is True and propio["puede_escribir"] is False


async def test_opciones_sin_token_es_401_y_sin_profesional_asociado_403(client, mundo, session_factory) -> None:
    assert (await client.get(URL + "/opciones")).status_code == 401
    _, token = await crear_usuario_panel(session_factory, "huerfano@turnos.test", ["odontologo"])
    assert (await client.get(URL + "/opciones", headers=bearer(token))).status_code == 403
