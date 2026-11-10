"""C-06 (6.1): acreditación de la seña con anti-solape (servicio único). PostgreSQL real, sin red."""

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select, update

from app.models.core import RegistroAuditoria
from app.pagos.service import acreditar_pago
from app.turnos.models import Turno
from tests.conftest import bearer
from tests.sena_helpers import (
    fecha_laboral, forzar_vencimiento, iniciar, local, pagos_de, reservar, sembrar_agenda, turno_de,
)


async def _preparar(client, ids, factory, hhmm="10:00", medio="mercadopago", nombre="Carlos Sintético"):
    f = fecha_laboral()
    reserva = await reservar(client, ids, local(f, hhmm), nombre)
    r = await iniciar(client, reserva, medio)
    assert r.status_code == 201, r.text
    return f, reserva, r.json()["pago_id"]


async def _acreditar(factory, pago_id, **kw):
    kw.setdefault("monto_reportado", Decimal("3000.00"))  # la pasarela informa monto y moneda (RN-SN-09)
    kw.setdefault("moneda_reportada", "ARS")
    async with factory() as s:
        return await acreditar_pago(s, pago_id, **kw)


async def _auditoria(factory, turno_id, origen):
    async with factory() as s:
        filas = await s.execute(select(RegistroAuditoria).where(
            RegistroAuditoria.entidad == "turno", RegistroAuditoria.entidad_id == str(turno_id),
            RegistroAuditoria.datos_despues["origen"].astext == origen))
        return list(filas.scalars().all())


async def test_acreditar_un_en_espera_libre_lo_reserva_y_bloquea_la_agenda(
        client, seed_ids, session_factory, pasarela, token_recepcion) -> None:
    f = fecha_laboral()
    await sembrar_agenda(session_factory, seed_ids, f)
    _, reserva, pago_id = await _preparar(client, seed_ids, session_factory)
    r = await _acreditar(session_factory, pago_id, mp_payment_id="PAY-1")
    assert r.efecto == "acreditado"

    turno = await turno_de(session_factory, reserva["turno_id"])
    assert turno.estado == "reservado" and turno.en_espera_vence_en is None
    (pago,) = await pagos_de(session_factory, reserva["turno_id"])
    assert pago.estado == "acreditado" and pago.mp_payment_id == "PAY-1" and pago.acreditado_en is not None
    # el horario sale de la disponibilidad pública
    d = await client.get("/api/public/disponibilidad", params={
        "profesional_id": seed_ids["profesional_id"], "tratamiento_id": seed_ids["tratamiento_id"],
        "desde": f.isoformat(), "hasta": f.isoformat()})
    assert local(f, "10:00") not in [datetime.fromisoformat(s["inicio"]) for s in d.json()["slots"]]
    # y un alta interna solapada da 409 (R5)
    solapado = await client.post("/api/turnos", json={
        "profesional_id": seed_ids["profesional_id"], "sillon_id": seed_ids["sillon_id"],
        "tratamiento_id": seed_ids["tratamiento_id"], "inicio": local(f, "10:15").isoformat()},
        headers=bearer(token_recepcion))
    assert solapado.status_code == 409


async def test_dos_en_espera_en_el_mismo_horario_gana_el_primero_en_acreditarse(
        client, seed_ids, session_factory, pasarela) -> None:
    f = fecha_laboral()
    await sembrar_agenda(session_factory, seed_ids, f)
    _, a, pago_a = await _preparar(client, seed_ids, session_factory, nombre="Paciente Uno")
    _, b, pago_b = await _preparar(client, seed_ids, session_factory, nombre="Paciente Dos")
    assert (await _acreditar(session_factory, pago_b, mp_payment_id="PAY-B")).efecto == "acreditado"
    perdedor = await _acreditar(session_factory, pago_a, mp_payment_id="PAY-A")
    assert perdedor.efecto == "a_reembolsar"  # P3 / RN-SN-05

    assert (await turno_de(session_factory, b["turno_id"])).estado == "reservado"
    assert (await turno_de(session_factory, a["turno_id"])).estado == "cancelado"
    (pa,) = await pagos_de(session_factory, a["turno_id"])
    assert pa.estado == "a_reembolsar" and pa.mp_payment_id == "PAY-A"
    async with session_factory() as s:
        bloqueantes = (await s.execute(select(func.count()).select_from(Turno)
                                       .where(Turno.estado.in_(("reservado", "confirmado"))))).scalar_one()
    assert bloqueantes == 1
    assert await _auditoria(session_factory, a["turno_id"], "acreditacion_sena") == []


async def test_sillon_original_ocupado_y_otro_libre_reasigna_y_lo_audita(
        client, seed_pair, session_factory, pasarela) -> None:
    ids = {"profesional_id": seed_pair["p1"], "sillon_id": seed_pair["s1"], "tratamiento_id": seed_pair["t"]}
    f = fecha_laboral()
    await sembrar_agenda(session_factory, ids, f)
    _, reserva, pago_id = await _preparar(client, ids, session_factory)
    assert (await turno_de(session_factory, reserva["turno_id"])).sillon_id == seed_pair["s1"]  # tentativo
    async with session_factory() as s:  # otro profesional toma S1 en ese horario
        s.add(Turno(profesional_id=seed_pair["p2"], sillon_id=seed_pair["s1"], tratamiento_id=seed_pair["t"],
                    inicio=local(f, "10:00"), fin=local(f, "10:30"), estado="reservado"))
        await s.commit()
    assert (await _acreditar(session_factory, pago_id, mp_payment_id="PAY-1")).efecto == "acreditado"
    turno = await turno_de(session_factory, reserva["turno_id"])
    assert turno.estado == "reservado" and turno.sillon_id == seed_pair["s2"]
    (aud,) = await _auditoria(session_factory, reserva["turno_id"], "acreditacion_sena")
    assert aud.datos_antes["sillon_id"] == seed_pair["s1"] and aud.datos_despues["sillon_id"] == seed_pair["s2"]
    assert aud.datos_despues["estado"] == "reservado"


async def test_sin_sillon_libre_el_turno_se_cancela_y_el_pago_queda_a_reembolsar(
        client, seed_pair, session_factory, pasarela) -> None:
    ids = {"profesional_id": seed_pair["p1"], "sillon_id": seed_pair["s1"], "tratamiento_id": seed_pair["t"]}
    f = fecha_laboral()
    await sembrar_agenda(session_factory, ids, f)
    _, reserva, pago_id = await _preparar(client, ids, session_factory)
    async with session_factory() as s:  # P2 ocupa S1 y S2 queda inactivo: no hay sillón
        s.add(Turno(profesional_id=seed_pair["p2"], sillon_id=seed_pair["s1"], tratamiento_id=seed_pair["t"],
                    inicio=local(f, "10:00"), fin=local(f, "10:30"), estado="reservado"))
        from app.turnos.models import Sillon
        await s.execute(update(Sillon).where(Sillon.id == seed_pair["s2"]).values(estado="inactivo"))
        await s.commit()
    assert (await _acreditar(session_factory, pago_id, mp_payment_id="PAY-1")).efecto == "a_reembolsar"
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "cancelado"
    (pago,) = await pagos_de(session_factory, reserva["turno_id"])
    assert pago.estado == "a_reembolsar"


async def test_pago_sobre_turno_vencido_o_cancelado_queda_a_reembolsar_sin_revivir_el_turno(
        client, seed_ids, session_factory, pasarela) -> None:
    f = fecha_laboral()
    await sembrar_agenda(session_factory, seed_ids, f)
    _, vencido, pago_v = await _preparar(client, seed_ids, session_factory, "10:00")
    _, cancelado, pago_c = await _preparar(client, seed_ids, session_factory, "11:00")
    await forzar_vencimiento(session_factory, vencido["turno_id"], datetime.now(timezone.utc) - timedelta(minutes=1))
    async with session_factory() as s:
        await s.execute(update(Turno).where(Turno.id == cancelado["turno_id"])
                        .values(estado="cancelado", en_espera_vence_en=None))
        await s.commit()

    assert (await _acreditar(session_factory, pago_v, mp_payment_id="PAY-V")).efecto == "a_reembolsar"
    assert (await _acreditar(session_factory, pago_c, mp_payment_id="PAY-C")).efecto == "a_reembolsar"
    for turno_id, esperado in ((vencido["turno_id"], "cancelado"), (cancelado["turno_id"], "cancelado")):
        assert (await turno_de(session_factory, turno_id)).estado == esperado
        (pago,) = await pagos_de(session_factory, turno_id)
        assert pago.estado == "a_reembolsar"
    async with session_factory() as s:
        assert (await s.execute(select(func.count()).select_from(Turno)
                                .where(Turno.estado.in_(("reservado", "confirmado"))))).scalar_one() == 0


async def test_acreditar_dos_veces_el_mismo_pago_es_no_op_con_una_sola_auditoria(
        client, seed_ids, session_factory, pasarela) -> None:
    f = fecha_laboral()
    await sembrar_agenda(session_factory, seed_ids, f)
    _, reserva, pago_id = await _preparar(client, seed_ids, session_factory)
    assert (await _acreditar(session_factory, pago_id, mp_payment_id="PAY-1")).efecto == "acreditado"
    assert (await _acreditar(session_factory, pago_id, mp_payment_id="PAY-1")).efecto == "sin_cambios"
    assert len(await _auditoria(session_factory, reserva["turno_id"], "acreditacion_sena")) == 1
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "reservado"


async def test_dos_acreditaciones_concurrentes_del_mismo_pago_tienen_un_solo_efecto(
        client, seed_ids, session_factory, pasarela) -> None:
    f = fecha_laboral()
    await sembrar_agenda(session_factory, seed_ids, f)
    for _ in range(3):  # repetir: una carrera acertada una vez no demuestra nada
        async with session_factory() as s:
            await s.execute(Turno.__table__.delete().where(Turno.estado != "x"))  # limpia entre vueltas
            await s.commit()
        _, reserva, pago_id = await _preparar(client, seed_ids, session_factory)
        resultados = await asyncio.gather(
            _acreditar(session_factory, pago_id, mp_payment_id="PAY-1"),
            _acreditar(session_factory, pago_id, mp_payment_id="PAY-1"),
        )
        assert sorted(r.efecto for r in resultados) == ["acreditado", "sin_cambios"]
        assert len(await _auditoria(session_factory, reserva["turno_id"], "acreditacion_sena")) == 1
        # limpiar el pago para poder borrar el turno en la próxima vuelta
        from app.pagos.models import AprobacionPago, PagoSena
        async with session_factory() as s:
            await s.execute(AprobacionPago.__table__.delete())
            await s.execute(PagoSena.__table__.delete())
            await s.commit()


async def test_acreditaciones_concurrentes_de_dos_pre_reservas_del_mismo_horario_dejan_un_solo_bloqueante(
        client, seed_ids, session_factory, pasarela) -> None:
    f = fecha_laboral()
    await sembrar_agenda(session_factory, seed_ids, f)
    _, a, pago_a = await _preparar(client, seed_ids, session_factory, nombre="Paciente Uno")
    _, b, pago_b = await _preparar(client, seed_ids, session_factory, nombre="Paciente Dos")
    resultados = await asyncio.gather(
        _acreditar(session_factory, pago_a, mp_payment_id="PAY-A"),
        _acreditar(session_factory, pago_b, mp_payment_id="PAY-B"),
    )  # nunca 500 ni deadlock: el advisory lock serializa
    assert sorted(r.efecto for r in resultados) == ["a_reembolsar", "acreditado"]
    async with session_factory() as s:
        assert (await s.execute(select(func.count()).select_from(Turno)
                                .where(Turno.estado == "reservado"))).scalar_one() == 1


async def test_pre_reserva_que_vence_sin_pagar_no_deja_auditoria_de_acreditacion(
        client, seed_ids, session_factory, pasarela) -> None:
    f = fecha_laboral()
    await sembrar_agenda(session_factory, seed_ids, f)
    reserva = await reservar(client, seed_ids, local(f, "10:00"))
    assert await _auditoria(session_factory, reserva["turno_id"], "acreditacion_sena") == []


async def test_pago_vencido_por_cambio_de_medio_igual_se_acredita_si_el_turno_sigue_vigente(
        client, seed_ids, session_factory, pasarela) -> None:
    """El paciente pagó por MP aunque ya había pasado a transferencia: el dinero llegó y el turno sigue vivo."""
    from tests.sena_helpers import configurar_transferencia
    f = fecha_laboral()
    await sembrar_agenda(session_factory, seed_ids, f)
    await configurar_transferencia(session_factory)
    _, reserva, pago_mp = await _preparar(client, seed_ids, session_factory)
    assert (await iniciar(client, reserva, "transferencia")).status_code == 201
    assert (await _acreditar(session_factory, pago_mp, mp_payment_id="PAY-1")).efecto == "acreditado"
    pagos = await pagos_de(session_factory, reserva["turno_id"])
    assert sorted((p.medio, p.estado) for p in pagos) == [("mercadopago", "acreditado"), ("transferencia", "vencido")]
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "reservado"
