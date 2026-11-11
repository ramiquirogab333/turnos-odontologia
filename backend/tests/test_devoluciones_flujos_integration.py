"""C-12 (4.4 y 4.5): los pendientes salen de los flujos REALES de C-06 (no de filas insertadas). Datos sintéticos (R19).

Regla de D5: cada importe adeudado figura exactamente una vez, con su tipo.
"""

import asyncio
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select

from app.pagos.models import AprobacionPago
from app.pagos.service import cambiar_estado_turno
from tests.conftest import bearer
from tests.sena_helpers import (
    configurar_transferencia, fecha_laboral, forzar_vencimiento, iniciar, local, pagos_de, reservar, sembrar_agenda,
    turno_de,
)
from tests.test_sena_revision_monto_integration import _con_pago, _enviar

BASE = "/api/panel/caja"


async def _pendientes(client, token: str) -> list[tuple[str, str | None, int]]:
    r = await client.get(f"{BASE}/pendientes", headers=bearer(token))
    assert r.status_code == 200, r.text
    return sorted((x["tipo"], x["importe"], x["pago_id"]) for x in r.json())


async def _cancelar(factory, turno_id: int, horas_antes: int):  # type: ignore[no-untyped-def]
    inicio = (await turno_de(factory, turno_id)).inicio
    async with factory() as s:
        return await cambiar_estado_turno(s, turno_id, "cancelado", None, ahora=inicio - timedelta(hours=horas_antes))


async def test_caso_1_cancelacion_de_una_sena_por_transferencia(client, seed_ids, session_factory, pasarela, token_recepcion) -> None:  # type: ignore[no-untyped-def]
    f = fecha_laboral()
    await sembrar_agenda(session_factory, seed_ids, f)
    await configurar_transferencia(session_factory)
    reserva = await reservar(client, seed_ids, local(f, "10:00"))
    pago_id = (await iniciar(client, reserva, "transferencia")).json()["pago_id"]
    assert (await client.post(f"/api/admin/pagos-sena/{pago_id}/acreditar", headers=bearer(token_recepcion))).status_code == 200
    await _cancelar(session_factory, reserva["turno_id"], 48)
    assert await _pendientes(client, token_recepcion) == [("sena", "3000.00", pago_id)]


async def test_caso_2_cancelacion_de_una_sena_de_mercado_pago_no_genera_excedente(client, seed_ids, session_factory, pasarela, token_recepcion) -> None:  # type: ignore[no-untyped-def]
    reserva, ref = await _con_pago(client, seed_ids, session_factory)
    assert (await _enviar(client, f"fake-approved-{ref}@3000.00@ARS")).json()["status"] == "acreditado"
    await _cancelar(session_factory, reserva["turno_id"], 48)
    [pago] = await pagos_de(session_factory, reserva["turno_id"])
    assert await _pendientes(client, token_recepcion) == [("sena", "3000.00", pago.id)]


async def test_caso_3_pago_tardio_despues_de_cancelar(client, seed_ids, session_factory, pasarela, token_recepcion) -> None:  # type: ignore[no-untyped-def]
    reserva, ref = await _con_pago(client, seed_ids, session_factory)
    await _cancelar(session_factory, reserva["turno_id"], 3)
    assert (await _enviar(client, f"fake-approved-{ref}@3000.00@ARS")).json()["status"] == "a_reembolsar"
    [pago] = await pagos_de(session_factory, reserva["turno_id"])
    assert pago.acreditado_en is not None  # el instante en que llegó el dinero
    assert await _pendientes(client, token_recepcion) == [("sena", "3000.00", pago.id)]


async def test_caso_4_horario_perdido_contra_otra_pre_reserva(client, seed_ids, session_factory, pasarela, token_recepcion) -> None:  # type: ignore[no-untyped-def]
    f = fecha_laboral()
    await sembrar_agenda(session_factory, seed_ids, f)
    a = await reservar(client, seed_ids, local(f, "10:00"), "Paciente Uno")
    b = await reservar(client, seed_ids, local(f, "10:00"), "Paciente Dos")
    pago_a = (await iniciar(client, a, "mercadopago")).json()
    pago_b = (await iniciar(client, b, "mercadopago")).json()
    assert (await _enviar(client, f"fake-approved-{pago_b['referencia_externa']}@3000.00@ARS")).json()["status"] == "acreditado"
    assert (await _enviar(client, f"fake-approved-{pago_a['referencia_externa']}@3000.00@ARS")).json()["status"] == "a_reembolsar"
    assert await _pendientes(client, token_recepcion) == [("sena", "3000.00", pago_a["pago_id"])]


async def test_caso_5_revision_cancelada_junto_con_la_pre_reserva(client, seed_ids, session_factory, pasarela, token_recepcion) -> None:  # type: ignore[no-untyped-def]
    reserva, ref = await _con_pago(client, seed_ids, session_factory)
    assert (await _enviar(client, f"fake-approved-{ref}@2500.00@ARS")).json()["status"] == "en_revision"
    assert [x[0] for x in await _pendientes(client, token_recepcion)] == ["revision"]
    await _cancelar(session_factory, reserva["turno_id"], 3)
    [pago] = await pagos_de(session_factory, reserva["turno_id"])
    assert await _pendientes(client, token_recepcion) == [("sena", "2500.00", pago.id)]


async def test_caso_6_revision_aceptada_tarde_con_el_turno_vencido(client, seed_ids, session_factory, pasarela, token_recepcion) -> None:  # type: ignore[no-untyped-def]
    reserva, ref = await _con_pago(client, seed_ids, session_factory)
    assert (await _enviar(client, f"fake-approved-{ref}@2500.00@ARS")).json()["status"] == "en_revision"
    [pago] = await pagos_de(session_factory, reserva["turno_id"])
    await forzar_vencimiento(session_factory, reserva["turno_id"], (await turno_de(session_factory, reserva["turno_id"])).inicio - timedelta(days=30))
    r = await client.post(f"/api/admin/pagos-sena/{pago.id}/acreditar", headers=bearer(token_recepcion))
    assert r.status_code == 200 and r.json()["estado_pago"] == "a_reembolsar"
    assert await _pendientes(client, token_recepcion) == [("sena", "2500.00", pago.id)]


async def test_caso_7_excedentes_sobre_una_sena_acreditada_y_sobre_una_a_reembolsar(client, seed_ids, session_factory, pasarela, token_recepcion) -> None:  # type: ignore[no-untyped-def]
    # (a) seña acreditada + un segundo pago aprobado con otro id
    reserva, ref = await _con_pago(client, seed_ids, session_factory)
    assert (await _enviar(client, f"fake-approved-{ref}@3000.00@ARS")).json()["status"] == "acreditado"
    assert (await _enviar(client, f"fake-approved-{ref}@3000.000@ARS")).json()["status"] == "a_reembolsar"
    [pago] = await pagos_de(session_factory, reserva["turno_id"])
    assert pago.estado == "acreditado"
    assert await _pendientes(client, token_recepcion) == [("excedente_mp", "3000.00", pago.id)]
    # (b) la misma seña cancelada con 48 h: ahora debe la seña Y el excedente, cada uno una vez
    await _cancelar(session_factory, reserva["turno_id"], 48)
    assert await _pendientes(client, token_recepcion) == [("excedente_mp", "3000.00", pago.id),
                                                          ("sena", "3000.00", pago.id)]


async def test_rechazo_y_acreditacion_simultaneos_dejan_un_solo_resultado(client, seed_ids, session_factory, pasarela, token_recepcion) -> None:  # type: ignore[no-untyped-def]
    reserva, ref = await _con_pago(client, seed_ids, session_factory)
    assert (await _enviar(client, f"fake-approved-{ref}@2500.00@ARS")).json()["status"] == "en_revision"
    [pago] = await pagos_de(session_factory, reserva["turno_id"])
    rechazo, acreditacion = await asyncio.gather(
        client.post(f"{BASE}/revisiones/{pago.id}/rechazar", headers=bearer(token_recepcion)),
        client.post(f"/api/admin/pagos-sena/{pago.id}/acreditar", headers=bearer(token_recepcion)))
    assert sorted([rechazo.status_code, acreditacion.status_code]) == [200, 409]
    [final] = await pagos_de(session_factory, reserva["turno_id"])
    assert final.estado == ("a_reembolsar" if rechazo.status_code == 200 else "acreditado")


# --- 4.5 sellado de acreditado_en en la cancelación de una pre-reserva con pago en revisión -------------------------

async def test_cancelar_una_pre_reserva_con_pago_en_revision_sella_acreditado_en_y_devuelve_todos_sus_pagos(client, seed_ids, session_factory, pasarela) -> None:  # type: ignore[no-untyped-def]
    reserva, ref = await _con_pago(client, seed_ids, session_factory)
    assert (await _enviar(client, f"fake-approved-{ref}@2500.00@ARS")).json()["status"] == "en_revision"
    assert (await _enviar(client, f"fake-approved-{ref}@2400.00@ARS")).json()["status"] == "en_revision"
    ahora = (await turno_de(session_factory, reserva["turno_id"])).inicio - timedelta(hours=3)
    async with session_factory() as s:
        await cambiar_estado_turno(s, reserva["turno_id"], "cancelado", None, ahora=ahora)
    [pago] = await pagos_de(session_factory, reserva["turno_id"])
    assert (pago.estado, pago.acreditado_en) == ("a_reembolsar", ahora)
    async with session_factory() as s:
        estados = (await s.execute(select(AprobacionPago.estado))).scalars().all()
    assert sorted(estados) == ["a_reembolsar", "a_reembolsar"]  # RN-SN-10: ninguno queda colgado en revisión
    assert Decimal("2500.00") == pago.monto_reportado
