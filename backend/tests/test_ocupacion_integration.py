"""C-12 (6.2, 6.4, 6.5, 6.7): ocupación por sillón y por día. Datos sintéticos (R19)."""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import delete, update

from app.models.core import Disponibilidad
from app.pagos.service import acreditar_pago
from app.turnos.models import Sillon
from tests.caja_helpers import en
from tests.clinica_helpers import Escenario, sembrar_escenario
from tests.conftest import bearer, crear_usuario_panel
from tests.panel_helpers import insertar_pago, insertar_turno, turno

D = date(2026, 11, 17)  # martes
AHORA = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
async def esc(session_factory, reloj) -> Escenario:  # type: ignore[no-untyped-def]
    reloj(AHORA)
    return await sembrar_escenario(session_factory)  # Sillón 1 y 2 activos; franjas 09-13 de Ana y de Bruno todos los días


async def ocupacion(client: AsyncClient, token: str, desde: date, hasta: date | None = None,
                    sillon_id: int | None = None) -> Response:
    params: dict[str, Any] = {"desde": desde.isoformat(), "hasta": (hasta or desde).isoformat()}
    if sillon_id is not None:
        params["sillon_id"] = sillon_id
    return await client.get("/api/panel/ocupacion", params=params, headers=bearer(token))


def dia_de(cuerpo: dict[str, Any], sillon_id: int, dia: date) -> dict[str, Any]:
    [s] = [x for x in cuerpo["sillones"] if x["sillon_id"] == sillon_id]
    [d] = [x for x in s["dias"] if x["dia"] == dia.isoformat()]
    return d


def resumen(d: dict[str, Any]) -> tuple[int, int, str | None, int]:
    return d["minutos_ocupados"], d["minutos_atencion"], d["porcentaje"], d["turnos"]


# --- 6.2 Ocupación por sillón y por día --------------------------------------------------------------------------

async def test_un_sillon_con_dos_turnos_informa_90_minutos_sobre_240_y_37_50_por_ciento(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await insertar_turno(session_factory, esc.mundo, en(D, "09:00"), minutos=30)
    await insertar_turno(session_factory, esc.mundo, en(D, "10:00"), minutos=60)
    r = await ocupacion(client, esc.recepcion, D)
    assert r.status_code == 200, r.text
    c = r.json()
    assert (c["desde"], c["hasta"]) == ("2026-11-17", "2026-11-17")
    assert resumen(dia_de(c, esc.mundo["s1"], D)) == (90, 240, "37.50", 2)
    assert resumen(dia_de(c, esc.mundo["s2"], D)) == (0, 240, "0.00", 0)
    assert [s["nombre"] for s in c["sillones"]] == ["Sillón 1", "Sillón 2"]


@pytest.mark.parametrize("desde,hasta,sillon", [("2026-11-01", "2026-12-02", None),   # 32 días
                                                ("2026-11-17", "2026-11-16", None),   # hasta anterior a desde
                                                ("2026-11-17", "2026-11-17", 999999),  # sillón inexistente
                                                ("17-11-2026", "2026-11-17", None)])
async def test_rango_o_sillon_invalidos_dan_422(client: AsyncClient, esc, desde: str, hasta: str, sillon: int | None) -> None:  # type: ignore[no-untyped-def]
    params: dict[str, Any] = {"desde": desde, "hasta": hasta}
    if sillon:
        params["sillon_id"] = sillon
    assert (await client.get("/api/panel/ocupacion", params=params, headers=bearer(esc.recepcion))).status_code == 422


async def test_un_rango_de_31_dias_se_acepta_y_trae_un_dia_por_sillon_y_dia(client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    r = await ocupacion(client, esc.recepcion, date(2026, 11, 1), date(2026, 12, 1))
    assert r.status_code == 200
    assert all(len(s["dias"]) == 31 for s in r.json()["sillones"])


async def test_un_turno_de_23_30_a_00_30_cuenta_el_dia_que_empieza_y_el_filtro_deja_solo_ese_sillon(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await insertar_turno(session_factory, esc.mundo, en(D, "23:30"), minutos=60, sillon="s2")
    r = await ocupacion(client, esc.recepcion, D, D + timedelta(days=1), sillon_id=esc.mundo["s2"])
    c = r.json()
    assert [s["sillon_id"] for s in c["sillones"]] == [esc.mundo["s2"]]
    assert dia_de(c, esc.mundo["s2"], D)["minutos_ocupados"] == 60
    assert (dia_de(c, esc.mundo["s2"], D + timedelta(days=1))["minutos_ocupados"],
            dia_de(c, esc.mundo["s2"], D + timedelta(days=1))["turnos"]) == (0, 0)


async def test_el_dia_de_un_turno_es_el_de_la_clinica_no_el_de_utc(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await insertar_turno(session_factory, esc.mundo, en(D, "22:00"), minutos=30)  # 01:00 UTC del 18
    c = (await ocupacion(client, esc.recepcion, D, D + timedelta(days=1))).json()
    assert dia_de(c, esc.mundo["s1"], D)["minutos_ocupados"] == 30
    assert dia_de(c, esc.mundo["s1"], D + timedelta(days=1))["minutos_ocupados"] == 0


# --- 6.4 Solo cuentan los turnos que ocupan agenda -------------------------------------------------------------

async def test_reservado_confirmado_y_atendido_suman_90_minutos(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    for hhmm, estado in (("09:00", "reservado"), ("09:30", "confirmado"), ("10:00", "atendido")):
        await insertar_turno(session_factory, esc.mundo, en(D, hhmm), estado=estado)
    d = dia_de((await ocupacion(client, esc.recepcion, D)).json(), esc.mundo["s1"], D)
    assert (d["minutos_ocupados"], d["turnos"], d["minutos_perdidos"]) == (90, 3, 0)


async def test_una_pre_reserva_en_espera_no_ocupa_nada_r8(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await insertar_turno(session_factory, esc.mundo, en(D, "09:00"), estado="en_espera", minutos=60,
                         vence=AHORA + timedelta(days=1))
    await insertar_turno(session_factory, esc.mundo, en(D, "11:00"), estado="cancelado", minutos=60)
    d = dia_de((await ocupacion(client, esc.recepcion, D)).json(), esc.mundo["s1"], D)
    assert resumen(d) == (0, 240, "0.00", 0)


async def test_al_acreditarse_la_pre_reserva_cuenta_y_un_ausente_suma_minutos_perdidos(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    turno_id = await insertar_turno(session_factory, esc.mundo, en(D, "09:00"), estado="en_espera", minutos=60,
                                    vence=AHORA + timedelta(days=1))
    pago_id = await insertar_pago(session_factory, turno_id, "pendiente")
    antes = dia_de((await ocupacion(client, esc.recepcion, D)).json(), esc.mundo["s1"], D)
    assert resumen(antes) == (0, 240, "0.00", 0)
    async with session_factory() as s:
        r = await acreditar_pago(s, pago_id, mp_payment_id="MP-SINT-1", monto_reportado=Decimal("3000.00"),
                                 moneda_reportada="ARS", ahora=AHORA)
    assert r.efecto == "acreditado" and (await turno(session_factory, turno_id)).estado == "reservado"
    await insertar_turno(session_factory, esc.mundo, en(D, "11:00"), estado="ausente", minutos=30)
    d = dia_de((await ocupacion(client, esc.recepcion, D)).json(), esc.mundo["s1"], D)
    assert (d["minutos_ocupados"], d["turnos"], d["minutos_perdidos"], d["porcentaje"]) == (60, 1, 30, "25.00")


# --- 6.5 Minutos de atención de un sillón -----------------------------------------------------------------------

async def test_franjas_superpuestas_de_dos_profesionales_dan_360_minutos_por_sillon_activo(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    async with session_factory() as s:
        await s.execute(update(Disponibilidad).where(Disponibilidad.profesional_id == esc.mundo["bruno"])
                        .values(hora_inicio=time(11, 0), hora_fin=time(15, 0)))
        await s.commit()
    c = (await ocupacion(client, esc.recepcion, D)).json()
    assert [dia_de(c, esc.mundo[s], D)["minutos_atencion"] for s in ("s1", "s2")] == [360, 360]


async def test_una_franja_inactiva_no_cuenta_como_atencion(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    async with session_factory() as s:
        await s.execute(update(Disponibilidad).where(Disponibilidad.profesional_id == esc.mundo["bruno"])
                        .values(is_active=False))
        await s.commit()
    assert dia_de((await ocupacion(client, esc.recepcion, D)).json(), esc.mundo["s1"], D)["minutos_atencion"] == 240


async def test_un_sillon_en_mantenimiento_con_un_turno_informa_ocupados_sin_atencion_ni_porcentaje(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    async with session_factory() as s:
        mant = Sillon(nombre="Sillón 3", estado="mantenimiento")
        inactivo = Sillon(nombre="Sillón 4", estado="inactivo")
        s.add_all([mant, inactivo])
        await s.flush()
        await s.commit()
        ids = {**esc.mundo, "s3": int(mant.id), "s4": int(inactivo.id)}
    await insertar_turno(session_factory, ids, en(D, "10:00"), estado="atendido", sillon="s3", prof="bruno")
    c = (await ocupacion(client, esc.recepcion, D)).json()
    assert resumen(dia_de(c, ids["s3"], D)) == (30, 0, None, 1)
    assert ids["s4"] not in [s["sillon_id"] for s in c["sillones"]]  # inactivo y sin turnos: no figura
    assert [s["estado"] for s in c["sillones"] if s["sillon_id"] == ids["s3"]] == ["mantenimiento"]


async def test_un_domingo_sin_franjas_informa_ceros_y_porcentaje_vacio(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    async with session_factory() as s:
        await s.execute(delete(Disponibilidad).where(Disponibilidad.dia_semana == 6))
        await s.commit()
    domingo = date(2026, 11, 22)
    c = (await ocupacion(client, esc.recepcion, domingo)).json()
    assert [resumen(dia_de(c, esc.mundo[s], domingo)) for s in ("s1", "s2")] == [(0, 0, None, 0)] * 2


async def test_dias_de_semana_distintos_usan_sus_propias_franjas(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    async with session_factory() as s:
        await s.execute(delete(Disponibilidad).where(Disponibilidad.dia_semana == D.weekday(),
                                                     Disponibilidad.profesional_id == esc.mundo["bruno"]))
        await s.execute(update(Disponibilidad).where(Disponibilidad.dia_semana == D.weekday())
                        .values(hora_fin=time(10, 0)))
        await s.commit()
    c = (await ocupacion(client, esc.recepcion, D, D + timedelta(days=1))).json()
    assert dia_de(c, esc.mundo["s1"], D)["minutos_atencion"] == 60
    assert dia_de(c, esc.mundo["s1"], D + timedelta(days=1))["minutos_atencion"] == 240


# --- 6.7 Solo recepción y admin ---------------------------------------------------------------------------------

async def test_admin_consulta_la_semana_la_odontologa_recibe_403_y_sin_token_401(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    assert (await ocupacion(client, esc.admin, D, D + timedelta(days=6))).status_code == 200
    r = await ocupacion(client, esc.ana, D)
    assert r.status_code == 403 and "sillones" not in r.text
    assert (await client.get("/api/panel/ocupacion", params={"desde": "2026-11-17", "hasta": "2026-11-17"})).status_code == 401
    _, doble = await crear_usuario_panel(session_factory, "doble@turnos.test", ["odontologo", "admin"])
    assert (await ocupacion(client, doble, D)).status_code == 200


async def test_la_respuesta_no_trae_nombres_ni_telefonos_de_pacientes(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await insertar_turno(session_factory, esc.mundo, en(D, "09:00"), nombre="Mateo Prueba", telefono="+5491100000012")
    r = await ocupacion(client, esc.recepcion, D)
    assert "Mateo" not in r.text and "5491100000012" not in r.text
