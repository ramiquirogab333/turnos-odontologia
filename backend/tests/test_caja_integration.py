"""C-12 (grupo 2): caja del día por concepto y medio. Datos sintéticos (R19)."""

from datetime import date, datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.clinica.service_pagos import resumen_por_dia_y_medio
from app.pagos.models import PagoSena
from tests.caja_helpers import (
    DIA,
    auditoria_de,
    caja,
    cobro,
    en,
    insertar_cierre,
    lineas_de,
    sena,
)
from tests.clinica_helpers import Escenario, crear_paciente, sembrar_escenario
from tests.conftest import bearer, crear_usuario_panel

AHORA = datetime(2026, 11, 19, 15, 0, tzinfo=timezone.utc)


@pytest.fixture
async def esc(session_factory, reloj) -> Escenario:  # type: ignore[no-untyped-def]
    reloj(AHORA)
    return await sembrar_escenario(session_factory)


# --- 2.3 Caja del día por concepto y medio ---------------------------------------------------------------------

async def test_dia_con_sena_y_cobro_devuelve_lineas_y_totales(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await sena(session_factory, esc, acreditado_en=en(DIA, "11:00"))
    await cobro(session_factory, fecha_cobro=en(DIA, "15:00"), monto="1500.00", medio="transferencia")
    r = await caja(client, esc.recepcion, DIA)
    assert r.status_code == 200, r.text
    c = r.json()
    assert lineas_de(c) == {("sena", "mercadopago"): (1, "3000.00"), ("pago_presupuesto", "transferencia"): (1, "1500.00")}
    assert (c["total_ingresos"], c["total_egresos"], c["total_neto"]) == ("4500.00", "0.00", "4500.00")
    assert c["dia"] == "2026-11-17"


@pytest.mark.parametrize("dia", ["17-11-2026", "2026-02-30", "mañana"])
async def test_dia_invalido_responde_422_sin_importes(session_factory, client: AsyncClient, esc, dia: str) -> None:  # type: ignore[no-untyped-def]
    await sena(session_factory, esc, acreditado_en=en(DIA, "11:00"))
    r = await caja(client, esc.recepcion, dia)
    assert r.status_code == 422
    assert "3000" not in r.text and "total_ingresos" not in r.text


async def test_dia_sin_movimientos_trae_lineas_vacias_y_ceros(client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    r = await caja(client, esc.recepcion, "2026-11-01")
    assert r.status_code == 200
    c = r.json()
    assert c["lineas"] == [] and c["movimientos"] == []
    assert (c["total_ingresos"], c["total_egresos"], c["total_neto"]) == ("0.00", "0.00", "0.00")
    assert c["senas_retenidas"] == {"cantidad": 0, "total": "0.00"}


async def test_los_totales_de_presupuestos_coinciden_con_el_contrato_de_c11(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    """La caja y ``resumen_por_dia_y_medio`` (contrato de C-11) suman lo mismo para el mismo día."""
    await cobro(session_factory, fecha_cobro=en(DIA, "10:00"), monto="1500.10", medio="transferencia")
    await cobro(session_factory, fecha_cobro=en(DIA, "11:00"), monto="2000.20", medio="mercadopago")
    c = (await caja(client, esc.recepcion, DIA)).json()
    desde, hasta = en(DIA, "00:00"), en(DIA + timedelta(days=1), "00:00")
    async with session_factory() as s:
        contrato = {t.medio: str(t.total) for t in await resumen_por_dia_y_medio(s, desde, hasta)}
    assert contrato == {"transferencia": "1500.10", "mercadopago": "2000.20"}
    assert lineas_de(c) == {("pago_presupuesto", "transferencia"): (1, "1500.10"),
                            ("pago_presupuesto", "mercadopago"): (1, "2000.20")}


# --- 2.5 Qué cuenta como ingreso y como egreso ----------------------------------------------------------------

async def test_sena_cobrada_un_dia_y_devuelta_otro_no_cambia_el_total_del_dia_original(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await sena(session_factory, esc, acreditado_en=en(DIA, "11:00"), estado="reembolsado", turno_estado="cancelado",
               reembolsado_en=en(date(2026, 11, 19), "10:00"), reembolso_referencia="DEV-SINT-0001")
    d17 = (await caja(client, esc.recepcion, "2026-11-17")).json()
    d19 = (await caja(client, esc.recepcion, "2026-11-19")).json()
    assert lineas_de(d17) == {("sena", "mercadopago"): (1, "3000.00")}
    assert (d17["total_ingresos"], d17["total_egresos"], d17["total_neto"]) == ("3000.00", "0.00", "3000.00")
    assert lineas_de(d19) == {("devolucion_sena", "mercadopago"): (1, "3000.00")}
    assert (d19["total_ingresos"], d19["total_egresos"], d19["total_neto"]) == ("0.00", "3000.00", "-3000.00")


async def test_en_revision_pendiente_vencido_y_cobro_anulado_no_suman(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await sena(session_factory, esc, acreditado_en=None, estado="en_revision", monto="3000.00",
               monto_reportado="2999.99", turno_estado="en_espera")
    await sena(session_factory, esc, acreditado_en=None, estado="pendiente", turno_estado="en_espera")
    await sena(session_factory, esc, acreditado_en=None, estado="vencido", turno_estado="cancelado")
    await cobro(session_factory, fecha_cobro=en(DIA, "12:00"), estado="anulado")
    c = (await caja(client, esc.recepcion, DIA)).json()
    assert c["lineas"] == [] and c["total_neto"] == "0.00"


async def test_una_sena_acreditada_a_mano_con_otro_importe_suma_lo_recibido(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await sena(session_factory, esc, acreditado_en=en(DIA, "13:00"), monto="3000.00", monto_reportado="2999.99")
    c = (await caja(client, esc.recepcion, DIA)).json()
    assert lineas_de(c) == {("sena", "mercadopago"): (1, "2999.99")} and c["total_ingresos"] == "2999.99"


async def test_un_pago_tardio_a_reembolsar_entra_el_dia_que_llego_y_sale_el_dia_de_la_devolucion(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await sena(session_factory, esc, acreditado_en=en(DIA, "20:00"), estado="a_reembolsar", turno_estado="cancelado")
    c = (await caja(client, esc.recepcion, DIA)).json()
    assert lineas_de(c) == {("sena", "mercadopago"): (1, "3000.00")}


# --- 2.6 La seña de un ausente queda retenida -----------------------------------------------------------------

async def test_marcar_ausente_deja_la_sena_como_ingreso_retenido_sin_egreso(session_factory, client: AsyncClient, esc, reloj) -> None:  # type: ignore[no-untyped-def]
    turno_id, pago_id = await sena(session_factory, esc, acreditado_en=en(date(2026, 11, 16), "11:00"),
                                   inicio=en(DIA, "10:00"))
    reloj(en(DIA, "12:00"))
    r = await client.post(f"/api/panel/turnos/{turno_id}/ausente", headers=bearer(esc.recepcion))
    assert r.status_code == 200 and r.json()["estado_sena"] == "no_reembolsado"
    c16 = (await caja(client, esc.recepcion, "2026-11-16")).json()
    assert lineas_de(c16) == {("sena", "mercadopago"): (1, "3000.00")} and c16["total_egresos"] == "0.00"
    assert c16["senas_retenidas"] == {"cantidad": 1, "total": "3000.00"}
    c17 = (await caja(client, esc.recepcion, "2026-11-17")).json()
    assert c17["senas_retenidas"] == {"cantidad": 0, "total": "0.00"}
    async with session_factory() as s:
        assert (await s.execute(select(PagoSena.estado).where(PagoSena.id == pago_id))).scalar_one() == "no_reembolsado"


async def test_ausente_sin_sena_no_genera_ningun_movimiento(session_factory, client: AsyncClient, esc, reloj) -> None:  # type: ignore[no-untyped-def]
    from tests.panel_helpers import insertar_turno

    turno_id = await insertar_turno(session_factory, esc.mundo, en(DIA, "10:00"), origen="manual")
    reloj(en(DIA, "12:00"))
    assert (await client.post(f"/api/panel/turnos/{turno_id}/ausente", headers=bearer(esc.recepcion))).status_code == 200
    c = (await caja(client, esc.recepcion, DIA)).json()
    assert c["lineas"] == [] and c["senas_retenidas"] == {"cantidad": 0, "total": "0.00"}


async def test_senas_retenidas_suma_varias_y_solo_las_del_dia_consultado(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await sena(session_factory, esc, acreditado_en=en(DIA, "09:00"), estado="no_reembolsado", turno_estado="ausente")
    await sena(session_factory, esc, acreditado_en=en(DIA, "10:00"), estado="no_reembolsado", turno_estado="ausente",
               monto="1000.50")
    await sena(session_factory, esc, acreditado_en=en(DIA + timedelta(days=1), "10:00"), estado="no_reembolsado",
               turno_estado="ausente")
    c = (await caja(client, esc.recepcion, DIA)).json()
    assert c["senas_retenidas"] == {"cantidad": 2, "total": "4000.50"}
    assert c["total_ingresos"] == "4000.50"


# --- 2.7 El día de la caja es el de la clínica ----------------------------------------------------------------

async def test_un_cobro_a_las_2230_de_la_clinica_figura_el_17_y_no_el_18(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    instante = en(DIA, "22:30")
    assert instante.astimezone(timezone.utc) == datetime(2026, 11, 18, 1, 30, tzinfo=timezone.utc)
    await sena(session_factory, esc, acreditado_en=instante)
    assert lineas_de((await caja(client, esc.recepcion, "2026-11-17")).json()) == {("sena", "mercadopago"): (1, "3000.00")}
    assert (await caja(client, esc.recepcion, "2026-11-18")).json()["lineas"] == []


async def test_primer_y_ultimo_instante_del_dia_entran_y_la_medianoche_siguiente_no(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await cobro(session_factory, fecha_cobro=en(DIA, "00:00"), monto="10.00")
    await cobro(session_factory, fecha_cobro=en(DIA, "23:59") + timedelta(seconds=59), monto="20.00")
    await cobro(session_factory, fecha_cobro=en(DIA + timedelta(days=1), "00:00"), monto="40.00")
    d17 = (await caja(client, esc.recepcion, "2026-11-17")).json()
    d18 = (await caja(client, esc.recepcion, "2026-11-18")).json()
    assert lineas_de(d17) == {("pago_presupuesto", "transferencia"): (2, "30.00")}
    assert lineas_de(d18) == {("pago_presupuesto", "transferencia"): (1, "40.00")}


async def test_sin_dia_usa_el_dia_actual_de_la_clinica_segun_el_reloj(session_factory, client: AsyncClient, esc, reloj) -> None:  # type: ignore[no-untyped-def]
    reloj(datetime(2026, 11, 18, 1, 30, tzinfo=timezone.utc))  # 22:30 del 17 en la clínica, ya 18 en UTC
    await sena(session_factory, esc, acreditado_en=en(DIA, "21:00"))
    c = (await caja(client, esc.recepcion)).json()
    assert c["dia"] == "2026-11-17" and lineas_de(c) == {("sena", "mercadopago"): (1, "3000.00")}


# --- 2.8 Detalle y acceso ---------------------------------------------------------------------------------------

async def test_el_detalle_trae_referencia_hora_con_offset_e_id_de_presupuesto_sin_datos_personales(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory, nombre="Lucía", apellido="Ejemplo", telefono="+5491100000011")
    presupuesto_id, _ = await cobro(session_factory, fecha_cobro=en(DIA, "15:30"), referencia="TRF-SINT-0001",
                                    paciente_id=paciente)
    turno_id, _ = await sena(session_factory, esc, acreditado_en=en(DIA, "09:15"))
    r = await caja(client, esc.recepcion, DIA)
    c = r.json()
    assert c["estado"] == "abierto" and c["cierre_id"] is None
    assert [(m["concepto"], m["hora"]) for m in c["movimientos"]] == [
        ("sena", "2026-11-17T09:15:00-03:00"), ("pago_presupuesto", "2026-11-17T15:30:00-03:00")]
    cobro_det = c["movimientos"][1]
    assert (cobro_det["referencia"], cobro_det["presupuesto_id"], cobro_det["importe"]) == (
        "TRF-SINT-0001", presupuesto_id, "1500.00")
    assert c["movimientos"][0]["turno_id"] == turno_id
    for dato in ("Lucía", "Ejemplo", "+5491100000011", "5491100000011", "lucia@ejemplo.test"):
        assert dato not in r.text


async def test_un_dia_con_cierre_vigente_figura_cerrado_con_su_id(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    anulado = await insertar_cierre(session_factory, DIA, estado="anulado")
    vigente = await insertar_cierre(session_factory, DIA)
    c = (await caja(client, esc.recepcion, DIA)).json()
    assert (c["estado"], c["cierre_id"]) == ("cerrado", vigente) and vigente != anulado
    otro = (await caja(client, esc.recepcion, "2026-11-16")).json()
    assert (otro["estado"], otro["cierre_id"]) == ("abierto", None)


async def test_recepcion_consulta_y_queda_auditado_lectura_caja(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    assert (await caja(client, esc.recepcion, DIA)).status_code == 200
    assert (await caja(client, esc.admin, DIA)).status_code == 200
    registros = await auditoria_de(session_factory, "lectura_caja")
    assert [(x.usuario_id, x.datos_despues) for x in registros] == [
        (esc.recepcion_id, {"dia": "2026-11-17"}), (esc.admin_id, {"dia": "2026-11-17"})]


async def test_la_odontologa_recibe_403_sin_importes_y_sin_auditoria(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await sena(session_factory, esc, acreditado_en=en(DIA, "11:00"))
    r = await caja(client, esc.ana, DIA)
    assert r.status_code == 403 and "3000" not in r.text
    assert await auditoria_de(session_factory, "lectura_caja") == []


async def test_sin_token_401_y_con_dos_roles_vale_el_permiso_mas_amplio(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    assert (await client.get("/api/panel/caja")).status_code == 401
    _, token = await crear_usuario_panel(session_factory, "doble@turnos.test", ["odontologo", "admin"])
    assert (await caja(client, token, DIA)).status_code == 200
