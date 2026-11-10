"""C-11 (grupo 8): pagos de presupuesto (saldo, tope, referencia única, anulación sin borrado). Datos sintéticos (R19)."""

import asyncio
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.clinica.models import PagoPresupuesto
from app.clinica.service_pagos import resumen_por_dia_y_medio
from tests.clinica_helpers import AHORA, Escenario, auditorias, contar, crear_paciente, hace, sembrar_escenario, turno_de
from tests.conftest import bearer
from tests.presupuestos_helpers import (
    aceptado, crear_presupuesto, insertar_pago, sembrar_catalogo, transicionar, tratamiento_sintetico,
)


@pytest.fixture
async def esc(session_factory, reloj) -> Escenario:  # type: ignore[no-untyped-def]
    reloj(AHORA)
    return await sembrar_escenario(session_factory)


@pytest.fixture
async def cat(session_factory, esc) -> dict[str, int]:  # type: ignore[no-untyped-def]
    return await sembrar_catalogo(session_factory)


@pytest.fixture
async def plan(session_factory, client: AsyncClient, esc, cat) -> dict[str, int]:  # type: ignore[no-untyped-def]
    """Paciente con Swiss y un presupuesto ACEPTADO de 4000.00 a su cargo (Limpieza + Consulta)."""
    paciente = await crear_paciente(session_factory, obra_social_id=cat["swiss"])
    pid = await aceptado(client, esc.recepcion, paciente, (cat["limpieza"], 1), (cat["consulta"], 1))
    return {"paciente": paciente, "presupuesto": pid}


def _url(plan: dict[str, int], resto: str = "") -> str:
    return f"/api/panel/pacientes/{plan['paciente']}/presupuestos/{plan['presupuesto']}/pagos{resto}"


def _pago(monto: str, medio: str = "transferencia", **extra: Any) -> dict[str, Any]:
    return {"medio": medio, "monto": monto, **extra}


# --- 8.1 / 8.2 Registro --------------------------------------------------------------------------------------

async def test_cobro_parcial_por_transferencia_deja_saldo_y_audita_sin_datos_del_paciente(session_factory, client: AsyncClient, esc, plan) -> None:  # type: ignore[no-untyped-def]
    resp = await client.post(_url(plan), json=_pago("1500.00", referencia="TRF-SINT-0001"),
                             headers=bearer(esc.recepcion))
    assert resp.status_code == 201, resp.text
    cuerpo = resp.json()
    assert (cuerpo["pago"]["monto"], cuerpo["pago"]["estado"], cuerpo["pago"]["referencia"]) == (
        "1500.00", "registrado", "TRF-SINT-0001")
    assert (cuerpo["total_pagado"], cuerpo["saldo"]) == ("1500.00", "2500.00")
    [registro] = await auditorias(session_factory, "registro_pago_presupuesto")
    assert (registro.usuario_id, registro.entidad, registro.entidad_id) == (
        esc.recepcion_id, "pago_presupuesto", str(cuerpo["pago"]["id"]))
    assert registro.datos_despues["monto"] == "1500.00"
    assert not {"nombre", "apellido", "dni", "telefono"} & set(registro.datos_despues)


async def test_pago_sobre_un_presupuesto_no_aceptado_409(session_factory, client: AsyncClient, esc, cat) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory, obra_social_id=cat["swiss"])
    pid = (await crear_presupuesto(client, esc.recepcion, paciente, (cat["limpieza"], 1))).json()["id"]
    await transicionar(client, esc.recepcion, paciente, pid, "presentar")
    resp = await client.post(f"/api/panel/pacientes/{paciente}/presupuestos/{pid}/pagos", json=_pago("100.00"),
                             headers=bearer(esc.recepcion))
    assert (resp.status_code, resp.json()["motivo"]) == (409, "presupuesto_no_aceptado")
    assert await contar(session_factory, "pago_presupuesto") == 0


@pytest.mark.parametrize("cuerpo", [_pago("100.00", medio="efectivo"), _pago("0.00"), _pago("-5.00"),
                                    _pago("10.123"), {"monto": "5.00"}])
async def test_cuerpo_invalido_422(session_factory, client: AsyncClient, esc, plan, cuerpo: dict[str, Any]) -> None:  # type: ignore[no-untyped-def]
    resp = await client.post(_url(plan), json=cuerpo, headers=bearer(esc.recepcion))
    assert resp.status_code == 422
    assert await contar(session_factory, "pago_presupuesto") == 0


async def test_la_odontologa_no_registra_ni_siendo_su_paciente(session_factory, client: AsyncClient, esc, plan) -> None:  # type: ignore[no-untyped-def]
    await turno_de(session_factory, esc, plan["paciente"], hace(dias=10))
    resp = await client.post(_url(plan), json=_pago("100.00"), headers=bearer(esc.ana))
    assert resp.status_code == 403
    assert await contar(session_factory, "pago_presupuesto") == 0


async def test_fecha_de_cobro_futura_422_e_igual_a_ahora_201(session_factory, client: AsyncClient, esc, plan) -> None:  # type: ignore[no-untyped-def]
    h = bearer(esc.recepcion)
    manana = await client.post(_url(plan), json=_pago("100.00", fecha_cobro=(AHORA + timedelta(days=1)).isoformat()),
                               headers=h)
    assert (manana.status_code, manana.json()["motivo"]) == (422, "fecha_cobro_futura")
    ahora = await client.post(_url(plan), json=_pago("100.00", fecha_cobro=AHORA.isoformat()), headers=h)
    assert ahora.status_code == 201
    sin_fecha = await client.post(_url(plan), json=_pago("100.00"), headers=h)
    assert sin_fecha.json()["pago"]["fecha_cobro"].startswith("2026-11-10T12:00:00")


async def test_sin_token_401_y_presupuesto_ajeno_404(session_factory, client: AsyncClient, esc, plan, cat) -> None:  # type: ignore[no-untyped-def]
    assert (await client.post(_url(plan), json=_pago("1.00"))).status_code == 401
    otro = await crear_paciente(session_factory, nombre="Mateo", apellido="Prueba")
    resp = await client.post(f"/api/panel/pacientes/{otro}/presupuestos/{plan['presupuesto']}/pagos",
                             json=_pago("1.00"), headers=bearer(esc.recepcion))
    assert resp.status_code == 404


# --- 8.3 Tope y concurrencia ---------------------------------------------------------------------------------

async def test_saldo_exacto_deja_cero_y_un_centavo_de_mas_409_con_saldo(session_factory, client: AsyncClient, esc, plan) -> None:  # type: ignore[no-untyped-def]
    h = bearer(esc.recepcion)
    await client.post(_url(plan), json=_pago("1500.00"), headers=h)  # saldo 2500.00
    mas = await client.post(_url(plan), json=_pago("2500.01", medio="mercadopago"), headers=h)
    assert (mas.status_code, mas.json()["motivo"], mas.json()["saldo"]) == (409, "monto_excede_saldo", "2500.00")
    assert await contar(session_factory, "pago_presupuesto") == 1
    exacto = await client.post(_url(plan), json=_pago("2500.00", medio="mercadopago"), headers=h)
    assert exacto.status_code == 201 and exacto.json()["saldo"] == "0.00"
    de_mas = await client.post(_url(plan), json=_pago("0.01"), headers=h)
    assert de_mas.status_code == 409 and de_mas.json()["saldo"] == "0.00"


async def test_dos_cobros_simultaneos_uno_201_y_otro_409_nunca_500(session_factory, client: AsyncClient, esc, cat) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory, obra_social_id=cat["swiss"])
    con_total_2500 = await tratamiento_sintetico(session_factory, "Tratamiento sintético 2500", "25000.00",
                                                 obra_social_id=cat["swiss"], cobertura="90.00")
    pid = await aceptado(client, esc.recepcion, paciente, (con_total_2500, 1))  # total a cargo 2500.00
    url = f"/api/panel/pacientes/{paciente}/presupuestos/{pid}/pagos"
    r1, r2 = await asyncio.gather(
        client.post(url, json=_pago("2000.00"), headers=bearer(esc.recepcion)),
        client.post(url, json=_pago("2000.00", medio="mercadopago"), headers=bearer(esc.admin)))
    assert sorted([r1.status_code, r2.status_code]) == [201, 409], (r1.text, r2.text)
    perdedor = r1 if r1.status_code == 409 else r2
    assert perdedor.json()["motivo"] == "monto_excede_saldo" and perdedor.json()["saldo"] == "500.00"
    leido = (await client.get(url, headers=bearer(esc.recepcion))).json()
    assert (leido["total_pagado"], leido["saldo"]) == ("2000.00", "500.00")


# --- 8.4 Referencia única por medio --------------------------------------------------------------------------

async def test_referencias_distintas_ok_y_repetida_409_aunque_sea_otro_presupuesto(session_factory, client: AsyncClient, esc, plan, cat) -> None:  # type: ignore[no-untyped-def]
    h = bearer(esc.recepcion)
    for ref in ("MP-SINT-0001", "MP-SINT-0002"):
        assert (await client.post(_url(plan), json=_pago("100.00", "mercadopago", referencia=ref),
                                  headers=h)).status_code == 201
    otro_paciente = await crear_paciente(session_factory, nombre="Mateo", apellido="Prueba", obra_social_id=cat["swiss"])
    otro = await aceptado(client, esc.recepcion, otro_paciente, (cat["limpieza"], 1))
    repetida = await client.post(f"/api/panel/pacientes/{otro_paciente}/presupuestos/{otro}/pagos",
                                 json=_pago("100.00", "mercadopago", referencia="MP-SINT-0001"), headers=h)
    assert (repetida.status_code, repetida.json()["motivo"]) == (409, "referencia_duplicada")
    mismo_ref_otro_medio = await client.post(_url(plan), json=_pago("100.00", "transferencia", referencia="MP-SINT-0001"),
                                             headers=h)
    assert mismo_ref_otro_medio.status_code == 201
    assert await contar(session_factory, "pago_presupuesto") == 3


async def test_la_referencia_de_un_pago_anulado_se_puede_reusar(session_factory, client: AsyncClient, esc, plan) -> None:  # type: ignore[no-untyped-def]
    h = bearer(esc.recepcion)
    primero = (await client.post(_url(plan), json=_pago("100.00", "mercadopago", referencia="MP-SINT-0001"),
                                 headers=h)).json()["pago"]["id"]
    assert (await client.post(_url(plan, f"/{primero}/anular"), json={"motivo": "cargado dos veces"},
                              headers=h)).status_code == 200
    nuevo = await client.post(_url(plan), json=_pago("100.00", "mercadopago", referencia="MP-SINT-0001"), headers=h)
    assert nuevo.status_code == 201


# --- 8.5 Anulación y consulta -------------------------------------------------------------------------------

async def test_anular_restituye_el_saldo_y_audita_sin_borrar(session_factory, client: AsyncClient, esc, plan) -> None:  # type: ignore[no-untyped-def]
    h = bearer(esc.recepcion)
    pago = (await client.post(_url(plan), json=_pago("1500.00"), headers=h)).json()["pago"]["id"]
    resp = await client.post(_url(plan, f"/{pago}/anular"), json={"motivo": "cargado en el presupuesto equivocado"},
                             headers=h)
    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    assert (cuerpo["pago"]["estado"], cuerpo["saldo"], cuerpo["total_pagado"]) == ("anulado", "4000.00", "0.00")
    assert cuerpo["pago"]["anulado_en"] is not None
    async with session_factory() as s:
        fila = (await s.execute(select(PagoPresupuesto).where(PagoPresupuesto.id == pago))).scalar_one()
    assert (fila.estado, fila.anulado_por, fila.anulado_motivo) == (
        "anulado", esc.recepcion_id, "cargado en el presupuesto equivocado")
    [registro] = await auditorias(session_factory, "anulacion_pago_presupuesto")
    assert registro.usuario_id == esc.recepcion_id and registro.entidad_id == str(pago)


async def test_doble_anulacion_409_y_motivo_vacio_422(session_factory, client: AsyncClient, esc, plan) -> None:  # type: ignore[no-untyped-def]
    h = bearer(esc.recepcion)
    pago = (await client.post(_url(plan), json=_pago("100.00"), headers=h)).json()["pago"]["id"]
    assert (await client.post(_url(plan, f"/{pago}/anular"), json={"motivo": ""}, headers=h)).status_code == 422
    assert (await client.post(_url(plan, f"/{pago}/anular"), json={"motivo": "error de carga"},
                              headers=h)).status_code == 200
    doble = await client.post(_url(plan, f"/{pago}/anular"), json={"motivo": "error de carga"}, headers=h)
    assert (doble.status_code, doble.json()["motivo"]) == (409, "transicion_invalida")
    assert len(await auditorias(session_factory, "anulacion_pago_presupuesto")) == 1


async def test_pago_de_otro_presupuesto_en_la_ruta_404(session_factory, client: AsyncClient, esc, plan, cat) -> None:  # type: ignore[no-untyped-def]
    h = bearer(esc.recepcion)
    otro = await aceptado(client, esc.recepcion, plan["paciente"], (cat["consulta"], 1))
    pago_de_otro = (await client.post(
        f"/api/panel/pacientes/{plan['paciente']}/presupuestos/{otro}/pagos", json=_pago("100.00"),
        headers=h)).json()["pago"]["id"]
    resp = await client.post(_url(plan, f"/{pago_de_otro}/anular"), json={"motivo": "ruta equivocada"}, headers=h)
    assert resp.status_code == 404
    async with session_factory() as s:
        assert (await s.get(PagoPresupuesto, pago_de_otro)).estado == "registrado"  # type: ignore[union-attr]


async def test_listado_con_registrados_anulados_total_y_saldo(session_factory, client: AsyncClient, esc, plan) -> None:  # type: ignore[no-untyped-def]
    h = bearer(esc.recepcion)
    await client.post(_url(plan), json=_pago("1500.00"), headers=h)
    anulado = (await client.post(_url(plan), json=_pago("500.00", "mercadopago"), headers=h)).json()["pago"]["id"]
    await client.post(_url(plan, f"/{anulado}/anular"), json={"motivo": "error de carga"}, headers=h)
    resp = await client.get(_url(plan), headers=h)
    cuerpo = resp.json()
    assert [p["estado"] for p in cuerpo["pagos"]] == ["registrado", "anulado"]
    assert (cuerpo["total_pagado"], cuerpo["saldo"]) == ("1500.00", "2500.00")
    assert len(await auditorias(session_factory, "lectura_pagos_presupuesto")) == 1


async def test_presupuesto_sin_pagos_lista_vacia_y_saldo_igual_al_total(client: AsyncClient, esc, plan) -> None:  # type: ignore[no-untyped-def]
    cuerpo = (await client.get(_url(plan), headers=bearer(esc.admin))).json()
    assert (cuerpo["pagos"], cuerpo["total_pagado"], cuerpo["saldo"]) == ([], "0.00", "4000.00")


async def test_la_odontologa_no_lee_ni_anula_pagos(session_factory, client: AsyncClient, esc, plan) -> None:  # type: ignore[no-untyped-def]
    pago = (await client.post(_url(plan), json=_pago("100.00"), headers=bearer(esc.recepcion))).json()["pago"]["id"]
    await turno_de(session_factory, esc, plan["paciente"], hace(dias=10))
    assert (await client.get(_url(plan), headers=bearer(esc.ana))).status_code == 403
    assert (await client.post(_url(plan, f"/{pago}/anular"), json={"motivo": "intento"},
                              headers=bearer(esc.ana))).status_code == 403
    async with session_factory() as s:
        assert (await s.get(PagoPresupuesto, pago)).estado == "registrado"  # type: ignore[union-attr]


# --- 8.6 Contrato para C-12 (caja) ---------------------------------------------------------------------------

async def test_resumen_por_dia_y_medio_ignora_anulados_y_usa_la_hora_de_la_clinica(session_factory, client: AsyncClient, esc, plan) -> None:  # type: ignore[no-untyped-def]
    from tests.panel_helpers import BA, local
    from datetime import date

    pid = plan["presupuesto"]
    dia = date(2026, 11, 3)
    # 23:30 hora de la clínica = 02:30 UTC del día siguiente: debe contar en el día 3, no en el 4
    await insertar_pago(session_factory, pid, "100.00", local(dia, "23:30"), "transferencia")
    await insertar_pago(session_factory, pid, "200.00", local(dia, "10:00"), "transferencia")
    await insertar_pago(session_factory, pid, "50.00", local(dia, "10:00"), "mercadopago")
    await insertar_pago(session_factory, pid, "70.00", local(date(2026, 11, 4), "00:15"), "transferencia")
    anulado = await insertar_pago(session_factory, pid, "999.00", local(dia, "12:00"), "transferencia")
    async with session_factory() as s:
        await s.execute(text("UPDATE pago_presupuesto SET estado='anulado', anulado_en=now(), "
                             "anulado_motivo='anulado de prueba' WHERE id=:i"), {"i": anulado})
        await s.commit()
    async with session_factory() as s:
        filas = await resumen_por_dia_y_medio(s, local(dia, "00:00"), local(date(2026, 11, 5), "00:00"))
    assert {(f.dia, f.medio): f.total for f in filas} == {
        (date(2026, 11, 3), "transferencia"): Decimal("300.00"), (date(2026, 11, 3), "mercadopago"): Decimal("50.00"),
        (date(2026, 11, 4), "transferencia"): Decimal("70.00")}
    assert BA.key == "America/Argentina/Buenos_Aires"


async def test_el_filtro_por_fecha_de_cobro_usa_el_indice(session_factory, client: AsyncClient, esc, plan) -> None:  # type: ignore[no-untyped-def]
    async with session_factory() as s:
        await s.execute(text(
            "INSERT INTO pago_presupuesto (presupuesto_id, medio, monto, estado, fecha_cobro) "
            "SELECT :p, 'transferencia', 1.00, 'registrado', CAST(:base AS timestamptz) + make_interval(mins => g) "
            "FROM generate_series(1, 1000) g"), {"p": plan["presupuesto"], "base": AHORA - timedelta(days=700)})
        await s.execute(text("ANALYZE pago_presupuesto"))
        await s.commit()
        explicacion = "\n".join((await s.execute(text(
            "EXPLAIN SELECT date_trunc('day', fecha_cobro), medio, sum(monto) FROM pago_presupuesto "
            "WHERE estado = 'registrado' AND fecha_cobro >= :a AND fecha_cobro < :b GROUP BY 1, 2"),
            {"a": AHORA - timedelta(days=10), "b": AHORA})).scalars())
    assert "ix_pago_presupuesto_fecha_cobro" in explicacion and "Seq Scan" not in explicacion
