"""C-12 (grupo 4): pendientes de la seña (en revisión y por devolver), rechazo, devoluciones y excedentes.

Los estados se fijan directamente (los flujos reales de C-06 están en ``test_devoluciones_flujos_integration.py``).
Datos sintéticos (R19).
"""

import asyncio
from datetime import date, datetime, timezone

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select

from app.pagos.models import AprobacionPago, PagoSena
from app.turnos.models import Turno
from tests.caja_helpers import DIA, aprobacion, auditoria_de, caja, en, insertar_cierre, lineas_de, sena
from tests.clinica_helpers import Escenario, sembrar_escenario
from tests.conftest import bearer

AHORA = datetime(2026, 11, 19, 15, 0, tzinfo=timezone.utc)  # 12:00 del 19 en la clínica
BASE = "/api/panel/caja"


@pytest.fixture
async def esc(session_factory, reloj) -> Escenario:  # type: ignore[no-untyped-def]
    reloj(AHORA)
    return await sembrar_escenario(session_factory)


async def pendientes(client: AsyncClient, token: str) -> Response:
    return await client.get(f"{BASE}/pendientes", headers=bearer(token))


async def rechazar(client: AsyncClient, token: str, pago_id: int) -> Response:
    return await client.post(f"{BASE}/revisiones/{pago_id}/rechazar", headers=bearer(token))


async def devolver(client: AsyncClient, token: str, pago_id: int, referencia: str | None = "DEV-SINT-0001",
                   **extra: object) -> Response:
    cuerpo: dict[str, object] = {**({} if referencia is None else {"referencia": referencia}), **extra}
    return await client.post(f"{BASE}/devoluciones/senas/{pago_id}", json=cuerpo, headers=bearer(token))


async def devolver_excedente(client: AsyncClient, token: str, aprobacion_id: int, referencia: str = "DEV-SINT-0002",
                             **extra: object) -> Response:
    return await client.post(f"{BASE}/devoluciones/excedentes/{aprobacion_id}",
                             json={"referencia": referencia, **extra}, headers=bearer(token))


async def pago_de(factory, pago_id: int) -> PagoSena:  # type: ignore[no-untyped-def]
    async with factory() as s:
        return (await s.execute(select(PagoSena).where(PagoSena.id == pago_id).execution_options(populate_existing=True))).scalar_one()


async def aprobacion_de(factory, aprobacion_id: int) -> AprobacionPago:  # type: ignore[no-untyped-def]
    async with factory() as s:
        return (await s.execute(select(AprobacionPago).where(AprobacionPago.id == aprobacion_id))).scalar_one()


async def estado_turno(factory, turno_id: int) -> str:  # type: ignore[no-untyped-def]
    async with factory() as s:
        return (await s.execute(select(Turno.estado).where(Turno.id == turno_id))).scalar_one()


# --- 4.2 Lista de pagos pendientes -------------------------------------------------------------------------------

async def test_la_lista_trae_una_revision_y_una_devolucion_ordenadas_por_antiguedad(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    turno_dev, pago_dev = await sena(session_factory, esc, acreditado_en=en(DIA, "11:00"), estado="a_reembolsar",
                                     turno_estado="cancelado", medio="transferencia", desde=en(DIA, "12:00"))
    turno_rev, pago_rev = await sena(session_factory, esc, acreditado_en=None, estado="en_revision",
                                     monto_reportado="2999.99", turno_estado="en_espera", mp_payment_id="MP-SINT-1",
                                     desde=en(DIA, "09:00"))
    r = await pendientes(client, esc.recepcion)
    assert r.status_code == 200, r.text
    primero, segundo = r.json()
    assert (primero["tipo"], primero["id"], primero["pago_id"], primero["turno_id"], primero["estado_turno"]) == (
        "revision", pago_rev, pago_rev, turno_rev, "en_espera")
    assert (primero["importe"], primero["importe_a_verificar"], primero["medio"], primero["mp_payment_id"]) == (
        "2999.99", False, "mercadopago", "MP-SINT-1")
    assert (segundo["tipo"], segundo["id"], segundo["importe"], segundo["medio"], segundo["estado_turno"]) == (
        "sena", pago_dev, "3000.00", "transferencia", "cancelado")
    assert segundo["mp_payment_id"] is None and primero["pendiente_desde"] < segundo["pendiente_desde"]
    for dato in ("Lucía", "Ejemplo", "5491100000011"):
        assert dato not in r.text
    assert turno_dev != turno_rev


async def test_los_excedentes_de_mercado_pago_figuran_con_su_importe_o_a_verificar(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    turno, pago = await sena(session_factory, esc, acreditado_en=en(DIA, "11:00"), mp_payment_id="MP-SINT-1")
    await aprobacion(session_factory, pago, "MP-SINT-1", estado="aplicado")  # el pago propio: no es excedente
    con_importe = await aprobacion(session_factory, pago, "MP-SINT-2", monto_reportado="3000.00", desde=en(DIA, "13:00"))
    sin_importe = await aprobacion(session_factory, pago, "MP-SINT-3", monto_reportado=None, desde=en(DIA, "14:00"))
    items = (await pendientes(client, esc.recepcion)).json()
    assert [(x["tipo"], x["id"], x["importe"], x["importe_a_verificar"], x["mp_payment_id"]) for x in items] == [
        ("excedente_mp", con_importe, "3000.00", False, "MP-SINT-2"),
        ("excedente_mp", sin_importe, None, True, "MP-SINT-3")]
    assert all(x["pago_id"] == pago and x["turno_id"] == turno and x["estado_turno"] == "reservado" for x in items)


async def test_la_odontologa_no_ve_los_pendientes_y_sin_token_es_401(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await sena(session_factory, esc, acreditado_en=en(DIA, "11:00"), estado="a_reembolsar", turno_estado="cancelado")
    r = await pendientes(client, esc.ana)
    assert r.status_code == 403 and "3000" not in r.text
    assert (await client.get(f"{BASE}/pendientes")).status_code == 401
    assert (await pendientes(client, esc.admin)).status_code == 200


async def test_una_revision_de_un_turno_vencido_sigue_listada_con_el_estado_cancelado(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await sena(session_factory, esc, acreditado_en=None, estado="en_revision", monto_reportado="2999.99",
               turno_estado="cancelado")
    [item] = (await pendientes(client, esc.recepcion)).json()
    assert (item["tipo"], item["estado_turno"], item["importe"]) == ("revision", "cancelado", "2999.99")


async def test_sin_pendientes_la_lista_esta_vacia_y_los_estados_resueltos_no_figuran(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await sena(session_factory, esc, acreditado_en=en(DIA, "11:00"))  # acreditado
    await sena(session_factory, esc, acreditado_en=en(DIA, "11:00"), estado="no_reembolsado", turno_estado="ausente")
    await sena(session_factory, esc, acreditado_en=en(DIA, "11:00"), estado="reembolsado", turno_estado="cancelado",
               reembolsado_en=en(DIA, "18:00"), reembolso_referencia="DEV-SINT-0009")
    await sena(session_factory, esc, acreditado_en=None, estado="vencido", turno_estado="cancelado")
    assert (await pendientes(client, esc.recepcion)).json() == []


# --- 4.5 Rechazar un pago en revisión --------------------------------------------------------------------------

async def test_rechazar_una_revision_la_pasa_a_a_reembolsar_por_lo_informado_sin_tocar_el_turno(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    turno, pago = await sena(session_factory, esc, acreditado_en=None, estado="en_revision", monto_reportado="2999.99",
                             turno_estado="en_espera", mp_payment_id="MP-SINT-1")
    propia = await aprobacion(session_factory, pago, "MP-SINT-1", estado="en_revision", monto_reportado="2999.99")
    otra = await aprobacion(session_factory, pago, "MP-SINT-2", estado="en_revision", monto_reportado="3000.00")
    r = await rechazar(client, esc.recepcion, pago)
    assert r.status_code == 200, r.text
    assert (r.json()["pago_id"], r.json()["estado_pago"], r.json()["estado_turno"], r.json()["importe"]) == (
        pago, "a_reembolsar", "en_espera", "2999.99")
    p = await pago_de(session_factory, pago)
    assert (p.estado, p.acreditado_en, p.acreditado_por_usuario_id) == ("a_reembolsar", AHORA, None)
    async with session_factory() as s:
        t = (await s.execute(select(Turno).where(Turno.id == turno))).scalar_one()
    assert t.estado == "en_espera" and t.en_espera_vence_en is not None  # R8: sigue sin ocupar agenda
    assert (await aprobacion_de(session_factory, propia)).estado == "a_reembolsar"
    assert (await aprobacion_de(session_factory, otra)).estado == "a_reembolsar"
    items = (await pendientes(client, esc.recepcion)).json()
    assert sorted((x["tipo"], x["id"], x["importe"]) for x in items) == [("excedente_mp", otra, "3000.00"), ("sena", pago, "2999.99")]


async def test_el_rechazo_deja_la_sena_como_ingreso_del_dia_del_rechazo(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    _, pago = await sena(session_factory, esc, acreditado_en=None, estado="en_revision", monto_reportado="2999.99",
                         turno_estado="en_espera")
    assert (await caja(client, esc.recepcion, "2026-11-19")).json()["lineas"] == []  # en revisión: fuera de los totales
    await rechazar(client, esc.recepcion, pago)
    assert lineas_de((await caja(client, esc.recepcion, "2026-11-19")).json()) == {("sena", "mercadopago"): (1, "2999.99")}


@pytest.mark.parametrize("estado", ["acreditado", "a_reembolsar", "no_reembolsado", "pendiente"])
async def test_un_pago_que_no_esta_en_revision_da_409_y_no_cambia(session_factory, client: AsyncClient, esc, estado: str) -> None:  # type: ignore[no-untyped-def]
    acreditado_en = None if estado == "pendiente" else en(DIA, "11:00")
    turno_estado = "en_espera" if estado == "pendiente" else "reservado"
    _, pago = await sena(session_factory, esc, acreditado_en=acreditado_en, estado=estado, turno_estado=turno_estado)
    r = await rechazar(client, esc.recepcion, pago)
    assert r.status_code == 409 and r.json()["motivo"] == "no_esta_en_revision"
    assert (await pago_de(session_factory, pago)).estado == estado
    assert await auditoria_de(session_factory, "sena_revision_rechazada") == []


async def test_rechazar_un_pago_inexistente_da_404(client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    r = await rechazar(client, esc.recepcion, 999999)
    assert r.status_code == 404 and r.json()["motivo"] == "pago_inexistente"


async def test_un_rechazo_repetido_da_409_la_segunda_vez(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    _, pago = await sena(session_factory, esc, acreditado_en=None, estado="en_revision", monto_reportado="2999.99",
                         turno_estado="en_espera")
    resultados = await asyncio.gather(rechazar(client, esc.recepcion, pago), rechazar(client, esc.admin, pago))
    assert sorted(r.status_code for r in resultados) == [200, 409]
    assert len(await auditoria_de(session_factory, "sena_revision_rechazada")) == 1


# --- 4.6 Registro de la devolución de una seña -----------------------------------------------------------------

async def test_la_devolucion_pasa_la_sena_a_reembolsado_con_usuario_fecha_y_referencia(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    turno, pago = await sena(session_factory, esc, acreditado_en=en(DIA, "11:00"), estado="a_reembolsar",
                             turno_estado="cancelado", medio="transferencia")
    r = await devolver(client, esc.recepcion, pago)
    assert r.status_code == 200, r.text
    assert (r.json()["pago_id"], r.json()["importe"], r.json()["referencia"]) == (pago, "3000.00", "DEV-SINT-0001")
    p = await pago_de(session_factory, pago)
    assert (p.estado, p.reembolsado_por_usuario_id, p.reembolsado_en, p.reembolso_referencia) == (
        "reembolsado", esc.recepcion_id, AHORA, "DEV-SINT-0001")
    assert await estado_turno(session_factory, turno) == "cancelado"  # el turno no revive
    assert (await pendientes(client, esc.recepcion)).json() == []


async def test_la_devolucion_usa_la_fecha_indicada_y_el_egreso_cae_ese_dia(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    _, pago = await sena(session_factory, esc, acreditado_en=en(DIA, "11:00"), estado="a_reembolsar",
                         turno_estado="cancelado")
    r = await devolver(client, esc.admin, pago, fecha=en(date(2026, 11, 18), "10:00").isoformat())
    assert r.status_code == 200
    d18 = (await caja(client, esc.recepcion, "2026-11-18")).json()
    assert lineas_de(d18) == {("devolucion_sena", "mercadopago"): (1, "3000.00")} and d18["total_egresos"] == "3000.00"
    d17 = (await caja(client, esc.recepcion, "2026-11-17")).json()
    assert d17["total_ingresos"] == "3000.00" and d17["total_egresos"] == "0.00"


@pytest.mark.parametrize("estado", ["acreditado", "no_reembolsado", "en_revision"])
async def test_una_sena_que_no_esta_por_devolverse_da_409_y_no_cambia_r9(session_factory, client: AsyncClient, esc, estado: str) -> None:  # type: ignore[no-untyped-def]
    en_rev = estado == "en_revision"
    _, pago = await sena(session_factory, esc, acreditado_en=None if en_rev else en(DIA, "11:00"), estado=estado,
                         turno_estado="en_espera" if en_rev else "reservado")
    r = await devolver(client, esc.recepcion, pago)
    assert r.status_code == 409 and r.json()["motivo"] == "no_es_devolucion_pendiente"
    p = await pago_de(session_factory, pago)
    assert (p.estado, p.reembolsado_en, p.reembolso_referencia) == (estado, None, None)
    assert (await caja(client, esc.recepcion, "2026-11-19")).json()["total_egresos"] == "0.00"


@pytest.mark.parametrize("cuerpo", [
    {"referencia": "DEV-SINT-0001", "fecha": "2026-11-20T10:00:00-03:00"},      # mañana
    {"referencia": "DEV-SINT-0001", "monto": "3000.00"},                        # importe enviado
    {"referencia": "ab"}, {"referencia": "x" * 65}, {"referencia": "   "}, {},   # referencia inválida o ausente
    {"referencia": "DEV-SINT-0001", "fecha": "2026-11-18T10:00:00"},            # sin zona horaria
    {"referencia": "DEV-SINT-0001", "fecha": "no-es-fecha"},
])
async def test_los_cuerpos_invalidos_dan_422_y_la_sena_sigue_a_reembolsar(session_factory, client: AsyncClient, esc, cuerpo: dict[str, object]) -> None:  # type: ignore[no-untyped-def]
    _, pago = await sena(session_factory, esc, acreditado_en=en(DIA, "11:00"), estado="a_reembolsar",
                         turno_estado="cancelado")
    r = await client.post(f"{BASE}/devoluciones/senas/{pago}", json=cuerpo, headers=bearer(esc.recepcion))
    assert r.status_code == 422
    assert (await pago_de(session_factory, pago)).estado == "a_reembolsar"


async def test_una_fecha_futura_o_anterior_a_la_recepcion_se_rechaza_con_su_motivo(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    _, pago = await sena(session_factory, esc, acreditado_en=en(DIA, "11:00"), estado="a_reembolsar",
                         turno_estado="cancelado")
    futura = await devolver(client, esc.recepcion, pago, fecha="2026-11-19T12:00:01-03:00")  # 1 s después de AHORA
    assert (futura.status_code, futura.json()["motivo"]) == (422, "fecha_futura")
    anterior = await devolver(client, esc.recepcion, pago, fecha=en(DIA, "10:59").isoformat())
    assert (anterior.status_code, anterior.json()["motivo"]) == (422, "fecha_anterior_a_la_recepcion")
    exacta = await devolver(client, esc.recepcion, pago, fecha=en(DIA, "11:00").isoformat())  # los límites se aceptan
    assert exacta.status_code == 200


async def test_una_devolucion_inexistente_da_404_y_una_segunda_da_409_sin_cambiar_la_referencia(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    _, pago = await sena(session_factory, esc, acreditado_en=en(DIA, "11:00"), estado="a_reembolsar",
                         turno_estado="cancelado")
    assert (await devolver(client, esc.recepcion, 999999)).status_code == 404
    assert (await devolver(client, esc.recepcion, pago, "DEV-SINT-0001")).status_code == 200
    r = await devolver(client, esc.admin, pago, "DEV-SINT-OTRA")
    assert r.status_code == 409 and r.json()["motivo"] == "no_es_devolucion_pendiente"
    assert (await pago_de(session_factory, pago)).reembolso_referencia == "DEV-SINT-0001"


async def test_dos_devoluciones_simultaneas_dejan_un_200_un_409_y_un_solo_egreso(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    _, pago = await sena(session_factory, esc, acreditado_en=en(DIA, "11:00"), estado="a_reembolsar",
                         turno_estado="cancelado")
    a, b = await asyncio.gather(devolver(client, esc.recepcion, pago, "DEV-SINT-0001"),
                                devolver(client, esc.admin, pago, "DEV-SINT-0002"))
    assert sorted([a.status_code, b.status_code]) == [200, 409]
    assert lineas_de((await caja(client, esc.recepcion, "2026-11-19")).json()) == {("devolucion_sena", "mercadopago"): (1, "3000.00")}
    assert len(await auditoria_de(session_factory, "devolucion_sena_registrada")) == 1


async def test_la_devolucion_de_una_sena_de_mp_cierra_tambien_su_aprobacion_propia_y_no_las_ajenas(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    _, pago = await sena(session_factory, esc, acreditado_en=en(DIA, "11:00"), estado="a_reembolsar",
                         turno_estado="cancelado", mp_payment_id="MP-SINT-1")
    propia = await aprobacion(session_factory, pago, "MP-SINT-1", estado="a_reembolsar")
    ajena = await aprobacion(session_factory, pago, "MP-SINT-2", estado="a_reembolsar")
    assert (await devolver(client, esc.recepcion, pago)).status_code == 200
    p = await aprobacion_de(session_factory, propia)
    assert (p.estado, p.reembolso_referencia, p.reembolsado_por_usuario_id) == ("reembolsado", "DEV-SINT-0001", esc.recepcion_id)
    assert (await aprobacion_de(session_factory, ajena)).estado == "a_reembolsar"
    assert [x["id"] for x in (await pendientes(client, esc.recepcion)).json()] == [ajena]


# --- 4.7 Bloqueo por día cerrado -------------------------------------------------------------------------------

async def test_una_devolucion_con_fecha_en_un_dia_abierto_es_egreso_de_ese_dia_aunque_haya_otros_cerrados(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await insertar_cierre(session_factory, DIA)
    _, pago = await sena(session_factory, esc, acreditado_en=en(DIA, "11:00"), estado="a_reembolsar",
                         turno_estado="cancelado")
    r = await devolver(client, esc.recepcion, pago, fecha=en(date(2026, 11, 19), "10:00").isoformat())
    assert r.status_code == 200
    assert (await caja(client, esc.recepcion, "2026-11-19")).json()["total_egresos"] == "3000.00"


async def test_una_devolucion_con_fecha_en_un_dia_cerrado_da_409_caja_cerrada_y_sigue_pendiente(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await insertar_cierre(session_factory, date(2026, 11, 18))
    _, pago = await sena(session_factory, esc, acreditado_en=en(DIA, "11:00"), estado="a_reembolsar",
                         turno_estado="cancelado")
    r = await devolver(client, esc.recepcion, pago, fecha=en(date(2026, 11, 18), "23:59").isoformat())
    assert r.status_code == 409 and (r.json()["motivo"], r.json()["dia"]) == ("caja_cerrada", "2026-11-18")
    assert (await pago_de(session_factory, pago)).estado == "a_reembolsar"
    assert [x["id"] for x in (await pendientes(client, esc.recepcion)).json()] == [pago]
    assert await auditoria_de(session_factory, "devolucion_sena_registrada") == []


# --- 4.8 Pagos excedentes de Mercado Pago ------------------------------------------------------------------------

async def test_la_devolucion_de_un_excedente_no_toca_la_sena_ni_el_turno_ni_la_caja(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    turno, pago = await sena(session_factory, esc, acreditado_en=en(DIA, "11:00"), mp_payment_id="MP-SINT-1")
    await aprobacion(session_factory, pago, "MP-SINT-1", estado="aplicado")
    exc = await aprobacion(session_factory, pago, "MP-SINT-2", monto_reportado="3000.00")
    antes = (await caja(client, esc.recepcion, "2026-11-17")).json()
    r = await devolver_excedente(client, esc.recepcion, exc)
    assert r.status_code == 200, r.text
    assert (r.json()["id"], r.json()["pago_id"], r.json()["turno_id"], r.json()["importe"], r.json()["referencia"]) == (
        exc, pago, turno, "3000.00", "DEV-SINT-0002")
    a = await aprobacion_de(session_factory, exc)
    assert (a.estado, a.reembolsado_por_usuario_id, a.reembolso_referencia, a.reembolsado_en) == (
        "reembolsado", esc.recepcion_id, "DEV-SINT-0002", AHORA)
    assert (await pago_de(session_factory, pago)).estado == "acreditado"
    assert await estado_turno(session_factory, turno) == "reservado"
    despues = (await caja(client, esc.recepcion, "2026-11-17")).json()
    assert (despues["lineas"], despues["total_neto"]) == (antes["lineas"], antes["total_neto"])
    assert (await caja(client, esc.recepcion, "2026-11-19")).json()["lineas"] == []
    assert (await pendientes(client, esc.recepcion)).json() == []


async def test_un_excedente_ya_devuelto_o_inexistente_o_propio_da_409_o_404(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    _, pago = await sena(session_factory, esc, acreditado_en=en(DIA, "11:00"), mp_payment_id="MP-SINT-1")
    propia = await aprobacion(session_factory, pago, "MP-SINT-1", estado="a_reembolsar")
    exc = await aprobacion(session_factory, pago, "MP-SINT-2")
    assert (await devolver_excedente(client, esc.recepcion, exc)).status_code == 200
    ya = await devolver_excedente(client, esc.recepcion, exc)
    assert (ya.status_code, ya.json()["motivo"]) == (409, "no_es_devolucion_pendiente")
    assert (await devolver_excedente(client, esc.recepcion, 999999)).status_code == 404
    # La aprobación del pago propio se resuelve como devolución de la seña, no como excedente.
    assert (await devolver_excedente(client, esc.recepcion, propia)).status_code == 409


async def test_un_excedente_sin_importe_informado_se_puede_devolver_igual(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    _, pago = await sena(session_factory, esc, acreditado_en=en(DIA, "11:00"), mp_payment_id="MP-SINT-1")
    exc = await aprobacion(session_factory, pago, "MP-SINT-2", monto_reportado=None)
    r = await devolver_excedente(client, esc.recepcion, exc)
    assert r.status_code == 200 and r.json()["importe"] is None


async def test_la_fecha_de_un_excedente_no_puede_ser_futura_ni_anterior_a_su_registro(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    _, pago = await sena(session_factory, esc, acreditado_en=en(DIA, "11:00"), mp_payment_id="MP-SINT-1")
    exc = await aprobacion(session_factory, pago, "MP-SINT-2", desde=en(DIA, "13:00"))
    r = await devolver_excedente(client, esc.recepcion, exc, fecha=en(DIA, "12:00").isoformat())
    assert (r.status_code, r.json()["motivo"]) == (422, "fecha_anterior_a_la_recepcion")
    r = await devolver_excedente(client, esc.recepcion, exc, fecha="2026-11-20T10:00:00-03:00")
    assert (r.status_code, r.json()["motivo"]) == (422, "fecha_futura")
    assert (await aprobacion_de(session_factory, exc)).estado == "a_reembolsar"


# --- 4.9 Roles y auditoría -------------------------------------------------------------------------------------

async def test_cada_resolucion_aceptada_queda_auditada_con_usuario_pago_turno_e_importe_sin_datos_personales(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    t_rev, rev = await sena(session_factory, esc, acreditado_en=None, estado="en_revision", monto_reportado="2999.99",
                            turno_estado="en_espera")
    t_dev, dev = await sena(session_factory, esc, acreditado_en=en(DIA, "11:00"), estado="a_reembolsar",
                            turno_estado="cancelado")
    t_exc, base = await sena(session_factory, esc, acreditado_en=en(DIA, "11:00"), mp_payment_id="MP-SINT-1")
    exc = await aprobacion(session_factory, base, "MP-SINT-2", monto_reportado="1234.50")
    await rechazar(client, esc.recepcion, rev)
    await devolver(client, esc.admin, dev)
    await devolver_excedente(client, esc.recepcion, exc)
    [a1] = await auditoria_de(session_factory, "sena_revision_rechazada")
    [a2] = await auditoria_de(session_factory, "devolucion_sena_registrada")
    [a3] = await auditoria_de(session_factory, "devolucion_excedente_registrada")
    assert (a1.usuario_id, a1.entidad, a1.entidad_id, a1.datos_despues) == (
        esc.recepcion_id, "pago_sena", str(rev), {"pago_id": rev, "turno_id": t_rev, "importe": "2999.99"})
    assert (a2.usuario_id, a2.entidad, a2.entidad_id, a2.datos_despues) == (
        esc.admin_id, "pago_sena", str(dev), {"pago_id": dev, "turno_id": t_dev, "importe": "3000.00"})
    assert (a3.usuario_id, a3.entidad, a3.entidad_id, a3.datos_despues) == (
        esc.recepcion_id, "pago_sena_aprobacion", str(exc), {"pago_id": base, "turno_id": t_exc, "importe": "1234.50"})
    for a in (a1, a2, a3):
        assert not {"nombre", "telefono", "dni", "email"} & set(a.datos_despues)


async def test_la_odontologa_no_resuelve_nada_sin_cambios_ni_auditoria(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    _, rev = await sena(session_factory, esc, acreditado_en=None, estado="en_revision", monto_reportado="2999.99",
                        turno_estado="en_espera")
    _, dev = await sena(session_factory, esc, acreditado_en=en(DIA, "11:00"), estado="a_reembolsar",
                        turno_estado="cancelado", mp_payment_id="MP-SINT-1")
    exc = await aprobacion(session_factory, dev, "MP-SINT-2")
    assert (await rechazar(client, esc.ana, rev)).status_code == 403
    assert (await devolver(client, esc.ana, dev)).status_code == 403
    assert (await devolver_excedente(client, esc.ana, exc)).status_code == 403
    assert (await client.post(f"{BASE}/revisiones/{rev}/rechazar")).status_code == 401
    assert (await pago_de(session_factory, rev)).estado == "en_revision"
    assert (await pago_de(session_factory, dev)).estado == "a_reembolsar"
    assert (await aprobacion_de(session_factory, exc)).estado == "a_reembolsar"
    for accion in ("sena_revision_rechazada", "devolucion_sena_registrada", "devolucion_excedente_registrada"):
        assert await auditoria_de(session_factory, accion) == []


async def test_las_operaciones_rechazadas_no_dejan_auditoria(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await insertar_cierre(session_factory, date(2026, 11, 18))
    _, acreditado = await sena(session_factory, esc, acreditado_en=en(DIA, "11:00"))
    _, dev = await sena(session_factory, esc, acreditado_en=en(DIA, "11:00"), estado="a_reembolsar",
                        turno_estado="cancelado")
    await devolver(client, esc.recepcion, acreditado)                                           # no_es_devolucion_pendiente
    await devolver(client, esc.recepcion, dev, fecha=en(date(2026, 11, 18), "10:00").isoformat())  # caja_cerrada
    await devolver(client, esc.recepcion, dev, referencia="ab")                                  # 422
    await rechazar(client, esc.recepcion, acreditado)                                           # no_esta_en_revision
    for accion in ("sena_revision_rechazada", "devolucion_sena_registrada", "devolucion_excedente_registrada"):
        assert await auditoria_de(session_factory, accion) == []


async def test_el_estado_reembolsado_es_final_para_la_agenda_y_para_la_aprobacion_de_un_pago_nuevo(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    """Una seña ``reembolsado`` no vuelve a ningún otro estado: ni por el rechazo ni por una nueva devolución."""
    _, pago = await sena(session_factory, esc, acreditado_en=en(DIA, "11:00"), estado="reembolsado",
                         turno_estado="cancelado", reembolsado_en=en(DIA, "18:00"), reembolso_referencia="DEV-SINT-0001")
    assert (await rechazar(client, esc.recepcion, pago)).status_code == 409
    assert (await devolver(client, esc.recepcion, pago, "DEV-SINT-NUEVA")).status_code == 409
    p = await pago_de(session_factory, pago)
    assert (p.estado, p.reembolso_referencia) == ("reembolsado", "DEV-SINT-0001")
