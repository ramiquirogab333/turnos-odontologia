"""C-06 (9.3): ``cambiar_estado_turno`` con los efectos sobre la seña (R9, RN-SN-02/04, RN-TU-01)."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.pagos.errores import TurnoInexistenteError
from app.pagos.estados import CancelacionFueraDePlazoError, TransicionInvalidaError
from app.pagos.service import acreditar_pago, cambiar_estado_turno
from tests.sena_helpers import (
    fecha_laboral, iniciar, local, pagos_de, reservar, sembrar_agenda, turno_de,
)


async def _reservado_con_sena(client, ids, factory, hhmm="10:00"):
    """Turno ``reservado`` con la seña de 3000.00 acreditada. Devuelve (reserva, inicio)."""
    f = fecha_laboral()
    await sembrar_agenda(factory, ids, f)
    reserva = await reservar(client, ids, local(f, hhmm))
    pago_id = (await iniciar(client, reserva, "mercadopago")).json()["pago_id"]
    async with factory() as s:
        await acreditar_pago(s, pago_id, mp_payment_id="PAY-1", monto_reportado=Decimal("3000.00"), moneda_reportada="ARS")
    return reserva, local(f, hhmm)


async def _cambiar(factory, turno_id, destino, ahora=None, usuario_id=None):
    async with factory() as s:
        return await cambiar_estado_turno(s, turno_id, destino, usuario_id, ahora=ahora)


async def test_confirmado_a_ausente_deja_la_sena_no_reembolsado_sin_pedir_reembolso(
        client, seed_ids, session_factory, pasarela) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    await _cambiar(session_factory, reserva["turno_id"], "confirmado")
    consultas_antes = (list(pasarela.consultas), list(pasarela.preferencias))
    r = await _cambiar(session_factory, reserva["turno_id"], "ausente", ahora=inicio + timedelta(minutes=10))
    assert (r.estado_turno, r.estado_pago) == ("ausente", "no_reembolsado")
    (pago,) = await pagos_de(session_factory, reserva["turno_id"])
    assert pago.estado == "no_reembolsado" and pago.monto == Decimal("3000.00")  # R9
    assert (list(pasarela.consultas), list(pasarela.preferencias)) == consultas_antes  # ningún reembolso a la pasarela
    assert not hasattr(pasarela, "reembolsar")


async def test_ausente_directo_desde_reservado_tambien_retiene_la_sena(
        client, seed_ids, session_factory, pasarela) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    await _cambiar(session_factory, reserva["turno_id"], "ausente", ahora=inicio + timedelta(minutes=5))
    assert (await pagos_de(session_factory, reserva["turno_id"]))[0].estado == "no_reembolsado"


async def test_en_espera_a_ausente_es_409_sin_cambios(client, seed_ids, session_factory, pasarela) -> None:
    f = fecha_laboral()
    await sembrar_agenda(session_factory, seed_ids, f)
    reserva = await reservar(client, seed_ids, local(f, "10:00"))
    await iniciar(client, reserva, "mercadopago")
    with pytest.raises(TransicionInvalidaError):
        await _cambiar(session_factory, reserva["turno_id"], "ausente")
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "en_espera"
    assert (await pagos_de(session_factory, reserva["turno_id"]))[0].estado == "pendiente"


async def test_en_espera_a_reservado_manual_no_existe_la_unica_via_es_la_acreditacion(
        client, seed_ids, session_factory, pasarela) -> None:
    f = fecha_laboral()
    await sembrar_agenda(session_factory, seed_ids, f)
    reserva = await reservar(client, seed_ids, local(f, "10:00"))
    with pytest.raises(TransicionInvalidaError):
        await _cambiar(session_factory, reserva["turno_id"], "reservado")
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "en_espera"


async def test_atendido_a_reservado_es_invalido(client, seed_ids, session_factory, pasarela) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    await _cambiar(session_factory, reserva["turno_id"], "atendido")
    for destino in ("reservado", "en_espera", "cancelado"):
        with pytest.raises(TransicionInvalidaError):
            await _cambiar(session_factory, reserva["turno_id"], destino, ahora=inicio - timedelta(days=3))
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "atendido"
    assert (await pagos_de(session_factory, reserva["turno_id"]))[0].estado == "acreditado"


async def test_cancelar_con_48h_devuelve_la_sena_y_libera_el_horario(
        client, seed_ids, session_factory, pasarela) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    r = await _cambiar(session_factory, reserva["turno_id"], "cancelado", ahora=inicio - timedelta(hours=48), usuario_id=None)
    assert (r.estado_turno, r.estado_pago) == ("cancelado", "a_reembolsar")
    (pago,) = await pagos_de(session_factory, reserva["turno_id"])
    assert pago.estado == "a_reembolsar" and pago.monto == Decimal("3000.00")  # RN-SN-04
    d = await client.get("/api/public/disponibilidad", params={
        "profesional_id": seed_ids["profesional_id"], "tratamiento_id": seed_ids["tratamiento_id"],
        "desde": inicio.date().isoformat(), "hasta": inicio.date().isoformat()})
    assert inicio in [datetime.fromisoformat(s["inicio"]) for s in d.json()["slots"]]  # horario libre otra vez


async def test_cancelar_con_23h59_es_fuera_de_plazo_y_no_cambia_nada(
        client, seed_ids, session_factory, pasarela) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    await _cambiar(session_factory, reserva["turno_id"], "confirmado")
    with pytest.raises(CancelacionFueraDePlazoError):
        await _cambiar(session_factory, reserva["turno_id"], "cancelado",
                       ahora=inicio - timedelta(hours=23, minutes=59))
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "confirmado"
    assert (await pagos_de(session_factory, reserva["turno_id"]))[0].estado == "acreditado"


async def test_cancelar_con_exactamente_24h_se_acepta(client, seed_ids, session_factory, pasarela) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    r = await _cambiar(session_factory, reserva["turno_id"], "cancelado", ahora=inicio - timedelta(hours=24))
    assert r.estado_pago == "a_reembolsar"


async def test_cancelar_una_pre_reserva_en_espera_vence_el_pago_sin_devolucion(
        client, seed_ids, session_factory, pasarela) -> None:
    f = fecha_laboral()
    await sembrar_agenda(session_factory, seed_ids, f)
    reserva = await reservar(client, seed_ids, local(f, "10:00"))
    await iniciar(client, reserva, "mercadopago")
    r = await _cambiar(session_factory, reserva["turno_id"], "cancelado")
    assert (r.estado_turno, r.estado_pago) == ("cancelado", "vencido")


async def test_turno_inexistente(client, seed_ids, session_factory, pasarela) -> None:
    with pytest.raises(TurnoInexistenteError):
        await _cambiar(session_factory, 999999, "cancelado")
