"""C-12 (6.6, 6.7): ausentismo del período y recupero por señas retenidas. Datos sintéticos (R19)."""

from datetime import date, datetime, timezone
from typing import Any

import pytest
from httpx import AsyncClient, Response

from tests.caja_helpers import en, sena
from tests.clinica_helpers import Escenario, sembrar_escenario
from tests.conftest import bearer, crear_usuario_panel
from tests.panel_helpers import insertar_turno

AHORA = datetime(2026, 11, 28, 12, 0, tzinfo=timezone.utc)
NOV = ("2026-11-01", "2026-11-30")


@pytest.fixture
async def esc(session_factory, reloj) -> Escenario:  # type: ignore[no-untyped-def]
    reloj(AHORA)
    return await sembrar_escenario(session_factory)


async def ausentismo(client: AsyncClient, token: str, desde: str = NOV[0], hasta: str = NOV[1]) -> Response:
    return await client.get("/api/panel/ausentismo", params={"desde": desde, "hasta": hasta}, headers=bearer(token))


async def turnos(factory, esc: Escenario, estado: str, cantidad: int, *, prof: str = "ana",  # type: ignore[no-untyped-def]
                 desde_dia: int = 2, **extra: Any) -> list[int]:
    """``cantidad`` turnos de 30 min en días distintos (sin solapes) a partir del ``desde_dia`` de noviembre."""
    ids = []
    for i in range(cantidad):
        ids.append(await insertar_turno(factory, esc.mundo, en(date(2026, 11, desde_dia + i), "10:00"), estado=estado,
                                        prof=prof, sillon="s1" if prof == "ana" else "s2", origen="manual", **extra))
    return ids


async def test_ocho_atendidos_y_dos_ausentes_dan_20_por_ciento_con_desglose_por_profesional(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await turnos(session_factory, esc, "atendido", 5, prof="ana", desde_dia=2)
    await turnos(session_factory, esc, "ausente", 1, prof="ana", desde_dia=10)
    await turnos(session_factory, esc, "atendido", 3, prof="bruno", desde_dia=2)
    await turnos(session_factory, esc, "ausente", 1, prof="bruno", desde_dia=10)
    r = await ausentismo(client, esc.recepcion)
    assert r.status_code == 200, r.text
    c = r.json()
    assert (c["atendidos"], c["ausentes"], c["tasa"], c["sin_marcar"]) == (8, 2, "20.00", 0)
    assert [(p["nombre"], p["atendidos"], p["ausentes"], p["tasa"]) for p in c["por_profesional"]] == [
        ("Dr. Bruno Ejemplo", 3, 1, "25.00"), ("Dra. Ana Ficticia", 5, 1, "16.67")]
    assert (c["desde"], c["hasta"]) == NOV


async def test_los_turnos_fuera_del_rango_no_cuentan_y_los_limites_del_dia_de_la_clinica_si(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await insertar_turno(session_factory, esc.mundo, en(date(2026, 10, 31), "23:59"), estado="atendido", origen="manual",
                         prof="bruno", sillon="s2")
    await insertar_turno(session_factory, esc.mundo, en(date(2026, 11, 1), "00:00"), estado="atendido", origen="manual")
    await insertar_turno(session_factory, esc.mundo, en(date(2026, 11, 30), "23:30"), estado="ausente", origen="manual",
                         prof="bruno", sillon="s2")
    await insertar_turno(session_factory, esc.mundo, en(date(2026, 12, 1), "00:00"), estado="ausente", origen="manual",
                         prof="bruno", sillon="s2")
    c = (await ausentismo(client, esc.recepcion)).json()
    assert (c["atendidos"], c["ausentes"], c["tasa"]) == (1, 1, "50.00")


@pytest.mark.parametrize("desde,hasta", [("2025-01-01", "2026-02-05"), ("2026-11-30", "2026-11-01"), ("2026-13-01", "2026-11-01")])
async def test_un_rango_invalido_o_de_400_dias_da_422(client: AsyncClient, esc, desde: str, hasta: str) -> None:  # type: ignore[no-untyped-def]
    assert (await ausentismo(client, esc.recepcion, desde, hasta)).status_code == 422


async def test_la_odontologa_recibe_403_y_sin_token_401(client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    r = await ausentismo(client, esc.ana)
    assert r.status_code == 403 and "tasa" not in r.text
    assert (await client.get("/api/panel/ausentismo", params={"desde": NOV[0], "hasta": NOV[1]})).status_code == 401


async def test_tres_terminados_sin_marcar_un_cancelado_y_una_pre_reserva_dejan_la_tasa_vacia(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await turnos(session_factory, esc, "reservado", 2, desde_dia=2)
    await turnos(session_factory, esc, "confirmado", 1, desde_dia=5)
    await turnos(session_factory, esc, "cancelado", 1, desde_dia=7)
    await turnos(session_factory, esc, "en_espera", 1, desde_dia=8, vence=en(date(2026, 11, 8), "09:00"))
    await insertar_turno(session_factory, esc.mundo, en(date(2026, 11, 29), "10:00"), estado="reservado",
                         origen="manual")  # todavía no terminó (ahora = 28 de noviembre): no es sin_marcar
    c = (await ausentismo(client, esc.recepcion, "2026-11-01", "2026-11-30")).json()
    assert (c["atendidos"], c["ausentes"], c["tasa"], c["sin_marcar"]) == (0, 0, None, 3)
    assert c["recupero"] == {"senas_retenidas": 0, "importe_retenido": "0.00", "porcentaje": None}


async def test_dos_ausentes_uno_con_sena_retenida_informan_1_3000_y_50_por_ciento(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await sena(session_factory, esc, acreditado_en=en(date(2026, 11, 1), "09:00"), estado="no_reembolsado",
               turno_estado="ausente", inicio=en(date(2026, 11, 10), "10:00"))
    await insertar_turno(session_factory, esc.mundo, en(date(2026, 11, 11), "10:00"), estado="ausente",
                         origen="manual")
    r = await ausentismo(client, esc.admin)
    c = r.json()
    assert (c["ausentes"], c["tasa"]) == (2, "100.00")
    assert c["recupero"] == {"senas_retenidas": 1, "importe_retenido": "3000.00", "porcentaje": "50.00"}


async def test_la_sena_retenida_suma_lo_recibido_y_no_cuenta_la_de_otro_periodo(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await sena(session_factory, esc, acreditado_en=en(date(2026, 11, 1), "09:00"), estado="no_reembolsado",
               turno_estado="ausente", inicio=en(date(2026, 11, 10), "10:00"), monto_reportado="2999.99")
    await sena(session_factory, esc, acreditado_en=en(date(2026, 10, 1), "09:00"), estado="no_reembolsado",
               turno_estado="ausente", inicio=en(date(2026, 10, 10), "10:00"))
    c = (await ausentismo(client, esc.recepcion)).json()
    assert c["recupero"] == {"senas_retenidas": 1, "importe_retenido": "2999.99", "porcentaje": "100.00"}


async def test_una_cancelacion_con_sena_a_reembolsar_no_es_ausente_ni_recupero(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await sena(session_factory, esc, acreditado_en=en(date(2026, 11, 1), "09:00"), estado="a_reembolsar",
               turno_estado="cancelado", inicio=en(date(2026, 11, 10), "10:00"))
    c = (await ausentismo(client, esc.recepcion)).json()
    assert (c["ausentes"], c["atendidos"], c["tasa"]) == (0, 0, None)
    assert c["recupero"] == {"senas_retenidas": 0, "importe_retenido": "0.00", "porcentaje": None}


async def test_sin_ausentes_el_recupero_es_cero_y_el_porcentaje_vacio(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await turnos(session_factory, esc, "atendido", 3)
    c = (await ausentismo(client, esc.recepcion)).json()
    assert (c["tasa"], c["recupero"]) == ("0.00", {"senas_retenidas": 0, "importe_retenido": "0.00", "porcentaje": None})


async def test_las_dos_respuestas_no_traen_nombres_ni_telefonos_de_pacientes_y_valen_dos_roles(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await turnos(session_factory, esc, "atendido", 1, nombre="Mateo Prueba", telefono="+5491100000012")
    await sena(session_factory, esc, acreditado_en=en(date(2026, 11, 1), "09:00"), estado="no_reembolsado",
               turno_estado="ausente", inicio=en(date(2026, 11, 12), "10:00"), nombre="Mateo Prueba",
               telefono="+5491100000012")
    for url, params in (("/api/panel/ausentismo", {"desde": NOV[0], "hasta": NOV[1]}),
                        ("/api/panel/ocupacion", {"desde": "2026-11-02", "hasta": "2026-11-12"})):
        r = await client.get(url, params=params, headers=bearer(esc.recepcion))
        assert r.status_code == 200 and "Mateo" not in r.text and "5491100000012" not in r.text, url
    _, doble = await crear_usuario_panel(session_factory, "doble@turnos.test", ["odontologo", "recepcion"])
    assert (await ausentismo(client, doble)).status_code == 200
