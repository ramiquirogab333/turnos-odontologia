"""C-12 (grupo 3): cierre de caja, anulación, consulta, liquidación y auditoría. Datos sintéticos (R19)."""

import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError

from app.caja.models import CierreCaja, CierreCajaLinea
from app.clinica.models import PagoPresupuesto
from tests.caja_helpers import DIA, auditoria_de, cobro, en, insertar_cierre, lineas_de, sena
from tests.clinica_helpers import Escenario, sembrar_escenario
from tests.conftest import bearer, crear_usuario_panel

AHORA = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)  # 09:00 del 18 en la clínica


@pytest.fixture
async def esc(session_factory, reloj) -> Escenario:  # type: ignore[no-untyped-def]
    reloj(AHORA)
    return await sembrar_escenario(session_factory)


async def cerrar(client: AsyncClient, token: str, dia: str | date, **extra: object) -> Response:
    return await client.post("/api/panel/caja/cierres", json={"dia": str(dia), **extra}, headers=bearer(token))


async def anular(client: AsyncClient, token: str, cierre_id: int, motivo: str = "cobro cargado en el presupuesto equivocado") -> Response:
    return await client.post(f"/api/panel/caja/cierres/{cierre_id}/anular", json={"motivo": motivo},
                             headers=bearer(token))


async def sembrar_dia_17(session_factory, esc) -> None:  # type: ignore[no-untyped-def]
    await sena(session_factory, esc, acreditado_en=en(DIA, "11:00"))
    await cobro(session_factory, fecha_cobro=en(DIA, "15:00"), monto="1500.00")


async def filas_de_cierre(session_factory, dia: date) -> list[CierreCaja]:  # type: ignore[no-untyped-def]
    async with session_factory() as s:
        return list((await s.execute(select(CierreCaja).where(CierreCaja.dia == dia).order_by(CierreCaja.id))).scalars())


# --- 3.2 Cierre de un día terminado ----------------------------------------------------------------------------

async def test_cierre_del_dia_anterior_devuelve_201_con_lineas_totales_usuario_e_instante(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await sembrar_dia_17(session_factory, esc)
    r = await cerrar(client, esc.recepcion, DIA, observaciones="cierre sintético")
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["estado"] == "vigente" and c["dia"] == "2026-11-17" and c["observaciones"] == "cierre sintético"
    assert lineas_de(c) == {("sena", "mercadopago"): (1, "3000.00"), ("pago_presupuesto", "transferencia"): (1, "1500.00")}
    assert (c["total_ingresos"], c["total_egresos"], c["total_neto"]) == ("4500.00", "0.00", "4500.00")
    assert c["cerrado_por"] == esc.recepcion_id and c["cerrado_en"]


async def test_dia_en_curso_da_409_con_el_instante_y_un_total_enviado_da_422_sin_crear_cierres(session_factory, client: AsyncClient, esc, reloj) -> None:  # type: ignore[no-untyped-def]
    reloj(en(DIA, "20:00"))
    r = await cerrar(client, esc.recepcion, DIA)
    assert r.status_code == 409
    assert (r.json()["motivo"], r.json()["cerrable_desde"]) == ("dia_no_terminado", "2026-11-18T00:15:00-03:00")
    assert (await cerrar(client, esc.recepcion, "2026-11-16", total_ingresos="1.00")).status_code == 422
    assert (await cerrar(client, esc.recepcion, "2026-11-30")).status_code == 409  # un día futuro tampoco
    async with session_factory() as s:
        assert (await s.execute(select(CierreCaja))).first() is None


async def test_limite_del_margen_a_las_0014_59_no_se_cierra_y_a_las_0015_00_si_con_cero_lineas(session_factory, client: AsyncClient, esc, reloj) -> None:  # type: ignore[no-untyped-def]
    reloj(en(DIA + timedelta(days=1), "00:14") + timedelta(seconds=59))
    assert (await cerrar(client, esc.recepcion, DIA)).status_code == 409
    reloj(en(DIA + timedelta(days=1), "00:15"))
    r = await cerrar(client, esc.recepcion, DIA)
    assert r.status_code == 201
    c = r.json()
    assert c["lineas"] == [] and (c["total_ingresos"], c["total_egresos"], c["total_neto"]) == ("0.00", "0.00", "0.00")


@pytest.mark.parametrize("cuerpo", [{}, {"dia": "17/11/2026"}, {"dia": "2026-11-17", "observaciones": "x" * 501},
                                    {"dia": "2026-11-17", "observaciones": ""}])
async def test_un_cuerpo_invalido_da_422(client: AsyncClient, esc, cuerpo: dict[str, object]) -> None:  # type: ignore[no-untyped-def]
    assert (await client.post("/api/panel/caja/cierres", json=cuerpo, headers=bearer(esc.recepcion))).status_code == 422


# --- 3.4 Un solo cierre vigente por día --------------------------------------------------------------------------

async def test_los_dias_se_cierran_en_cualquier_orden(client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    assert (await cerrar(client, esc.recepcion, "2026-11-16")).status_code == 201
    assert (await cerrar(client, esc.recepcion, "2026-11-15")).status_code == 201


async def test_repetir_el_cierre_de_un_dia_da_409_con_el_id_y_no_cambia_el_original(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    primero = (await cerrar(client, esc.recepcion, DIA)).json()
    r = await cerrar(client, esc.admin, DIA)
    assert r.status_code == 409
    assert (r.json()["motivo"], r.json()["cierre_id"]) == ("dia_ya_cerrado", primero["id"])
    [fila] = await filas_de_cierre(session_factory, DIA)
    assert (fila.id, fila.cerrado_por) == (primero["id"], esc.recepcion_id)


async def test_dos_cierres_simultaneos_dejan_un_201_un_409_y_un_unico_vigente(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    a, b = await asyncio.gather(cerrar(client, esc.recepcion, DIA), cerrar(client, esc.admin, DIA))
    assert sorted([a.status_code, b.status_code]) == [201, 409]
    assert [x.estado for x in await filas_de_cierre(session_factory, DIA)] == ["vigente"]


# --- 3.5 El cierre no se modifica --------------------------------------------------------------------------------

async def test_el_cierre_consultado_despues_trae_lo_mismo_que_al_crearse(session_factory, client: AsyncClient, esc, reloj) -> None:  # type: ignore[no-untyped-def]
    await sembrar_dia_17(session_factory, esc)
    creado = (await cerrar(client, esc.recepcion, DIA)).json()
    reloj(AHORA + timedelta(days=7))
    leido = (await client.get(f"/api/panel/caja/cierres/{creado['id']}", headers=bearer(esc.recepcion))).json()
    for campo in ("id", "dia", "estado", "total_ingresos", "total_egresos", "total_neto", "lineas", "cerrado_por",
                  "cerrado_en"):
        assert leido[campo] == creado[campo], campo


@pytest.mark.parametrize("metodo", ["put", "patch", "delete"])
async def test_editar_o_borrar_un_cierre_por_la_api_da_405(client: AsyncClient, esc, metodo: str) -> None:  # type: ignore[no-untyped-def]
    cierre = (await cerrar(client, esc.admin, DIA)).json()
    r = await client.request(metodo.upper(), f"/api/panel/caja/cierres/{cierre['id']}", headers=bearer(esc.admin))
    assert r.status_code == 405
    assert (await client.get(f"/api/panel/caja/cierres/{cierre['id']}", headers=bearer(esc.admin))).json()["estado"] == "vigente"


async def test_un_update_del_total_de_una_linea_o_del_cierre_lo_rechaza_la_base_desde_la_aplicacion(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await sembrar_dia_17(session_factory, esc)
    cierre = (await cerrar(client, esc.recepcion, DIA)).json()
    async with session_factory() as s:
        with pytest.raises(DBAPIError):
            await s.execute(update(CierreCajaLinea).where(CierreCajaLinea.cierre_id == cierre["id"])
                            .values(total=Decimal("1.00")))
        await s.rollback()
    async with session_factory() as s:
        with pytest.raises(DBAPIError):
            await s.execute(update(CierreCaja).where(CierreCaja.id == cierre["id"])
                            .values(total_ingresos=Decimal("1.00"), total_neto=Decimal("1.00")))
        await s.rollback()
    async with session_factory() as s:
        totales = (await s.execute(select(CierreCajaLinea.total).where(CierreCajaLinea.cierre_id == cierre["id"]))).scalars().all()
    assert sorted(str(t) for t in totales) == ["1500.00", "3000.00"]


# --- 3.6 El cierre cuadra ----------------------------------------------------------------------------------------

async def test_un_cierre_sin_cambios_cuadra(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await sembrar_dia_17(session_factory, esc)
    cierre = (await cerrar(client, esc.recepcion, DIA)).json()
    c = (await client.get(f"/api/panel/caja/cierres/{cierre['id']}", headers=bearer(esc.recepcion))).json()
    assert c["cuadra"] is True and c["diferencias"] == []


async def test_un_pago_anulado_fuera_de_la_aplicacion_hace_que_no_cuadre_y_lista_la_diferencia(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await sembrar_dia_17(session_factory, esc)
    cierre = (await cerrar(client, esc.recepcion, DIA)).json()
    async with session_factory() as s:
        await s.execute(update(PagoPresupuesto).values(estado="anulado", anulado_en=AHORA, anulado_motivo="error sintetico"))
        await s.commit()
    c = (await client.get(f"/api/panel/caja/cierres/{cierre['id']}", headers=bearer(esc.recepcion))).json()
    assert c["cuadra"] is False
    assert c["diferencias"] == [{"concepto": "pago_presupuesto", "medio": "transferencia", "total_cierre": "1500.00",
                                 "total_actual": "0.00", "cantidad_cierre": 1, "cantidad_actual": 0}]


async def test_marcar_ausente_y_devolver_otro_dia_no_descuadran_el_cierre(session_factory, client: AsyncClient, esc, reloj) -> None:  # type: ignore[no-untyped-def]
    turno_ausente, _ = await sena(session_factory, esc, acreditado_en=en(DIA, "11:00"), inicio=en(DIA, "12:00"))
    await sena(session_factory, esc, acreditado_en=en(DIA, "12:00"), estado="a_reembolsar", turno_estado="cancelado")
    cierre = (await cerrar(client, esc.recepcion, DIA)).json()
    reloj(en(date(2026, 11, 19), "10:00"))
    assert (await client.post(f"/api/panel/turnos/{turno_ausente}/ausente", headers=bearer(esc.recepcion))).status_code == 200
    async with session_factory() as s:
        await s.execute(text(
            "UPDATE pago_sena SET estado = 'reembolsado', reembolsado_en = :f, reembolso_referencia = 'DEV-SINT-0001' "
            "WHERE estado = 'a_reembolsar'"), {"f": en(date(2026, 11, 19), "09:00")})
        await s.commit()
    c = (await client.get(f"/api/panel/caja/cierres/{cierre['id']}", headers=bearer(esc.recepcion))).json()
    assert c["cuadra"] is True and c["total_ingresos"] == "6000.00"


async def test_un_cierre_anulado_informa_cuadra_nulo_y_un_id_inexistente_da_404(client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    cierre = (await cerrar(client, esc.recepcion, DIA)).json()
    assert (await anular(client, esc.admin, cierre["id"])).status_code == 200
    c = (await client.get(f"/api/panel/caja/cierres/{cierre['id']}", headers=bearer(esc.recepcion))).json()
    assert c["cuadra"] is None and c["diferencias"] == []
    assert (await client.get("/api/panel/caja/cierres/999999", headers=bearer(esc.recepcion))).status_code == 404


# --- 3.9 Carrera cierre contra movimiento ----------------------------------------------------------------------

@pytest.mark.parametrize("repeticion", range(10))
async def test_cierre_y_cobro_simultaneos_nunca_dejan_un_cobro_del_dia_fuera_del_cierre(session_factory, client: AsyncClient, esc, reloj, repeticion: int) -> None:  # type: ignore[no-untyped-def]
    reloj(datetime(2026, 12, 31, 12, 0, tzinfo=timezone.utc))
    dia = date(2026, 11, 1) + timedelta(days=repeticion)
    presupuesto_id, _ = await cobro(session_factory, fecha_cobro=en(dia, "08:00"), monto="100.00")
    async with session_factory() as s:
        paciente_id = (await s.execute(text("SELECT paciente_id FROM presupuesto WHERE id = :i"),
                                       {"i": presupuesto_id})).scalar_one()
    url = f"/api/panel/pacientes/{paciente_id}/presupuestos/{presupuesto_id}/pagos"
    nuevo = {"medio": "transferencia", "monto": "100.00", "fecha_cobro": en(dia, "09:00").isoformat()}
    cierre, pago = await asyncio.gather(cerrar(client, esc.recepcion, dia),
                                        client.post(url, json=nuevo, headers=bearer(esc.recepcion)))
    assert cierre.status_code == 201 and pago.status_code in (201, 409)
    cuerpo = cierre.json()
    if pago.status_code == 201:
        assert lineas_de(cuerpo)[("pago_presupuesto", "transferencia")] == (2, "200.00")
    else:
        assert pago.json()["motivo"] == "caja_cerrada"
        assert lineas_de(cuerpo)[("pago_presupuesto", "transferencia")] == (1, "100.00")


# --- 3.10 Anulación de un cierre ---------------------------------------------------------------------------------

async def test_admin_anula_y_se_vuelve_a_cerrar_quedando_un_anulado_y_un_vigente(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    cierre = (await cerrar(client, esc.recepcion, DIA)).json()
    r = await anular(client, esc.admin, cierre["id"])
    assert r.status_code == 200
    a = r.json()
    assert (a["estado"], a["anulado_por"], a["anulado_motivo"]) == (
        "anulado", esc.admin_id, "cobro cargado en el presupuesto equivocado") and a["anulado_en"]
    assert (await cerrar(client, esc.recepcion, DIA)).status_code == 201
    assert [x.estado for x in await filas_de_cierre(session_factory, DIA)] == ["anulado", "vigente"]


async def test_recepcion_no_anula_y_un_motivo_vacio_o_corto_da_422_y_el_cierre_sigue_vigente(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    cierre = (await cerrar(client, esc.recepcion, DIA)).json()
    assert (await anular(client, esc.recepcion, cierre["id"])).status_code == 403
    assert (await anular(client, esc.admin, cierre["id"], motivo="")).status_code == 422
    assert (await anular(client, esc.admin, cierre["id"], motivo="ab")).status_code == 422
    assert (await client.post(f"/api/panel/caja/cierres/{cierre['id']}/anular", json={"motivo": "motivo valido", "x": 1},
                              headers=bearer(esc.admin))).status_code == 422
    assert (await anular(client, esc.ana, cierre["id"])).status_code == 403
    assert [x.estado for x in await filas_de_cierre(session_factory, DIA)] == ["vigente"]


async def test_anular_dos_veces_da_409_transicion_invalida_y_un_id_inexistente_404(client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    cierre = (await cerrar(client, esc.recepcion, DIA)).json()
    assert (await anular(client, esc.admin, cierre["id"])).status_code == 200
    r = await anular(client, esc.admin, cierre["id"])
    assert r.status_code == 409 and r.json()["motivo"] == "transicion_invalida"
    assert (await anular(client, esc.admin, 999999)).status_code == 404


# --- 3.11 Consulta y auditoría ----------------------------------------------------------------------------------

async def test_los_cierres_del_mes_se_listan_del_mas_reciente_al_mas_antiguo(client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    for dia in ("2026-11-16", "2026-11-17"):
        await cerrar(client, esc.recepcion, dia)
    r = await client.get("/api/panel/caja/cierres", params={"desde": "2026-11-01", "hasta": "2026-11-30"},
                         headers=bearer(esc.recepcion))
    assert r.status_code == 200
    assert [x["dia"] for x in r.json()] == ["2026-11-17", "2026-11-16"]
    assert "lineas" not in r.json()[0]
    fuera = await client.get("/api/panel/caja/cierres", params={"desde": "2026-12-01", "hasta": "2026-12-31"},
                             headers=bearer(esc.recepcion))
    assert fuera.json() == []


@pytest.mark.parametrize("desde,hasta", [("2026-11-30", "2026-11-01"), ("2025-01-01", "2026-02-05"), ("x", "2026-11-01")])
async def test_un_rango_invalido_o_de_mas_de_366_dias_da_422(client: AsyncClient, esc, desde: str, hasta: str) -> None:  # type: ignore[no-untyped-def]
    r = await client.get("/api/panel/caja/cierres", params={"desde": desde, "hasta": hasta}, headers=bearer(esc.recepcion))
    assert r.status_code == 422


async def test_el_rango_de_366_dias_exactos_se_acepta_y_el_de_367_no(client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    ok = await client.get("/api/panel/caja/cierres", params={"desde": "2026-01-01", "hasta": "2027-01-01"}, headers=bearer(esc.recepcion))
    mal = await client.get("/api/panel/caja/cierres", params={"desde": "2026-01-01", "hasta": "2027-01-02"}, headers=bearer(esc.recepcion))
    assert (ok.status_code, mal.status_code) == (200, 422)


async def test_un_dia_con_un_anulado_y_un_vigente_lista_los_dos_con_el_motivo_del_anulado(client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    primero = (await cerrar(client, esc.recepcion, DIA)).json()
    await anular(client, esc.admin, primero["id"])
    await cerrar(client, esc.recepcion, DIA)
    r = await client.get("/api/panel/caja/cierres", params={"desde": "2026-11-17", "hasta": "2026-11-17"},
                         headers=bearer(esc.recepcion))
    por_estado = {x["estado"]: x for x in r.json()}
    assert set(por_estado) == {"anulado", "vigente"}
    assert por_estado["anulado"]["anulado_motivo"] == "cobro cargado en el presupuesto equivocado"
    assert por_estado["vigente"]["anulado_motivo"] is None


async def test_cierre_y_anulacion_quedan_auditados_sin_el_texto_del_motivo(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await sembrar_dia_17(session_factory, esc)
    cierre = (await cerrar(client, esc.recepcion, DIA)).json()
    await anular(client, esc.admin, cierre["id"], motivo="error de Lucía Ejemplo")
    [cerrado] = await auditoria_de(session_factory, "cierre_caja")
    [anulado] = await auditoria_de(session_factory, "anulacion_cierre_caja")
    assert (cerrado.usuario_id, cerrado.entidad, cerrado.entidad_id) == (esc.recepcion_id, "cierre_caja", str(cierre["id"]))
    assert cerrado.datos_despues == {"dia": "2026-11-17", "total_ingresos": "4500.00", "total_egresos": "0.00",
                                     "total_neto": "4500.00"}
    assert (anulado.usuario_id, anulado.entidad_id) == (esc.admin_id, str(cierre["id"]))
    assert anulado.datos_despues == {"dia": "2026-11-17"}
    assert "Lucía" not in str(anulado.datos_despues) and "Lucía" not in str(anulado.datos_antes)


async def test_los_cierres_rechazados_no_dejan_auditoria(session_factory, client: AsyncClient, esc, reloj) -> None:  # type: ignore[no-untyped-def]
    await cerrar(client, esc.recepcion, DIA)
    antes = len(await auditoria_de(session_factory, "cierre_caja"))
    assert (await cerrar(client, esc.recepcion, DIA)).status_code == 409  # dia_ya_cerrado
    reloj(en(DIA, "20:00"))
    assert (await cerrar(client, esc.recepcion, "2026-11-17")).status_code == 409
    assert (await cerrar(client, esc.recepcion, "2026-11-30")).status_code == 409  # dia_no_terminado
    assert len(await auditoria_de(session_factory, "cierre_caja")) == antes
    assert await auditoria_de(session_factory, "anulacion_cierre_caja") == []
    assert (await anular(client, esc.recepcion, 1)).status_code == 403
    assert await auditoria_de(session_factory, "anulacion_cierre_caja") == []


# --- 3.12 Liquidación por medio de pago -------------------------------------------------------------------------

async def test_la_liquidacion_de_dos_dias_consolida_por_medio(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    d16 = date(2026, 11, 16)
    await sena(session_factory, esc, acreditado_en=en(d16, "10:00"))
    await sena(session_factory, esc, acreditado_en=en(DIA, "10:00"))
    await cobro(session_factory, fecha_cobro=en(DIA, "15:00"), monto="1500.00")
    await cerrar(client, esc.recepcion, d16)
    await cerrar(client, esc.recepcion, DIA)
    r = await client.get("/api/panel/caja/liquidacion", params={"desde": "2026-11-16", "hasta": "2026-11-17"},
                         headers=bearer(esc.recepcion))
    assert r.status_code == 200, r.text
    c = r.json()
    por_medio = {m["medio"]: m for m in c["medios"]}
    assert (por_medio["mercadopago"]["neto"], por_medio["transferencia"]["neto"]) == ("6000.00", "1500.00")
    assert por_medio["mercadopago"]["detalle"] == [{"concepto": "sena", "cantidad": 2, "total": "6000.00"}]
    assert (c["total_ingresos"], c["total_egresos"], c["total_neto"]) == ("7500.00", "0.00", "7500.00")
    assert c["dias_sin_cierre"] == []


async def test_la_odontologa_no_pide_la_liquidacion(client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    r = await client.get("/api/panel/caja/liquidacion", params={"desde": "2026-11-16", "hasta": "2026-11-17"},
                         headers=bearer(esc.ana))
    assert r.status_code == 403 and "medios" not in r.text
    assert (await client.get("/api/panel/caja/liquidacion", params={"desde": "2026-11-16", "hasta": "2026-11-17"})).status_code == 401


async def test_liquidacion_con_dias_sin_cerrar_devoluciones_y_un_cierre_anulado_que_no_suma(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await cobro(session_factory, fecha_cobro=en(DIA, "10:00"), monto="1500.00", medio="transferencia")
    await sena(session_factory, esc, acreditado_en=en(DIA, "11:00"), estado="reembolsado", medio="transferencia",
               monto="500.00", turno_estado="cancelado", reembolsado_en=en(DIA, "18:00"),
               reembolso_referencia="DEV-SINT-0001")
    anulado = (await cerrar(client, esc.recepcion, "2026-11-16")).json()
    await anular(client, esc.admin, anulado["id"])
    await cerrar(client, esc.recepcion, DIA)
    r = await client.get("/api/panel/caja/liquidacion", params={"desde": "2026-11-16", "hasta": "2026-11-18"},
                         headers=bearer(esc.recepcion))
    c = r.json()
    [transferencia] = c["medios"]
    assert (transferencia["medio"], transferencia["ingresos"], transferencia["egresos"], transferencia["neto"]) == (
        "transferencia", "2000.00", "500.00", "1500.00")
    assert [x["concepto"] for x in transferencia["detalle"]] == ["sena", "pago_presupuesto", "devolucion_sena"]
    assert c["dias_sin_cierre"] == ["2026-11-16", "2026-11-18"]


@pytest.mark.parametrize("desde,hasta", [("2026-11-18", "2026-11-16"), ("2025-01-01", "2026-12-31")])
async def test_liquidacion_con_rango_invalido_da_422(client: AsyncClient, esc, desde: str, hasta: str) -> None:  # type: ignore[no-untyped-def]
    r = await client.get("/api/panel/caja/liquidacion", params={"desde": desde, "hasta": hasta}, headers=bearer(esc.admin))
    assert r.status_code == 422


async def test_el_cierre_y_la_liquidacion_son_solo_de_recepcion_y_admin(client: AsyncClient, esc, session_factory) -> None:  # type: ignore[no-untyped-def]
    cierre = await insertar_cierre(session_factory, DIA)
    for metodo, url, cuerpo in (("post", "/api/panel/caja/cierres", {"dia": "2026-11-16"}),
                                ("get", "/api/panel/caja/cierres?desde=2026-11-01&hasta=2026-11-30", None),
                                ("get", f"/api/panel/caja/cierres/{cierre}", None)):
        r = await client.request(metodo.upper(), url, json=cuerpo, headers=bearer(esc.ana))
        assert r.status_code == 403, url
        assert (await client.request(metodo.upper(), url, json=cuerpo)).status_code == 401, url
    _, doble = await crear_usuario_panel(session_factory, "doble@turnos.test", ["odontologo", "recepcion"])
    assert (await cerrar(client, doble, "2026-11-16")).status_code == 201
