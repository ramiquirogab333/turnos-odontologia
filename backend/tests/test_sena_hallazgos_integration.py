"""C-06 (grupo 15): hallazgos de la revisión de código (2, 3, 4, 7, 8). PostgreSQL real, sin red."""

import asyncio
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import event, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import RegistroAuditoria
from app.pagos import service as svc
from app.pagos.errores import OperacionReintentableError, PagoNoAcreditableError
from app.pagos.models import AprobacionPago, PagoSena
from app.pagos.pasarela import calcular_firma, verificar_firma
from app.pagos.service import acreditar_pago, acreditar_transferencia, cambiar_estado_turno
from tests.sena_helpers import (
    SECRETO_WEBHOOK, configurar_transferencia, fecha_laboral, forzar_vencimiento, iniciar, local, pagos_de,
    reservar, sembrar_agenda, turno_de,
)

OK = {"monto_reportado": Decimal("3000.00"), "moneda_reportada": "ARS"}


async def _pago_mp(client, ids, factory, hhmm="10:00"):
    f = fecha_laboral()
    await sembrar_agenda(factory, ids, f)
    await configurar_transferencia(factory)
    reserva = await reservar(client, ids, local(f, hhmm))
    r = await iniciar(client, reserva, "mercadopago")
    return reserva, r.json()["pago_id"], r.json()["referencia_externa"]


async def _acreditar(factory, pago_id, **kw):
    async with factory() as s:
        return await acreditar_pago(s, pago_id, **kw)


async def _aprobaciones(factory, pago_id):
    async with factory() as s:
        return list((await s.execute(select(AprobacionPago).where(AprobacionPago.pago_id == pago_id)
                                     .order_by(AprobacionPago.id))).scalars().all())


# --- Hallazgo 2: cada pago de MP se registra por su id --------------------------------------------------

async def test_segundo_pago_aprobado_distinto_sobre_un_pago_acreditado_queda_a_reembolsar(
        client, seed_ids, session_factory, pasarela) -> None:
    reserva, pago_id, _ = await _pago_mp(client, seed_ids, session_factory)
    assert (await _acreditar(session_factory, pago_id, mp_payment_id="PAY-1", **OK)).efecto == "acreditado"
    segundo = await _acreditar(session_factory, pago_id, mp_payment_id="PAY-2", **OK)
    assert segundo.efecto == "a_reembolsar"
    (pago,) = await pagos_de(session_factory, reserva["turno_id"])
    assert pago.estado == "acreditado" and pago.mp_payment_id == "PAY-1"  # el turno sigue reservado
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "reservado"
    assert [(a.mp_payment_id, a.estado) for a in await _aprobaciones(session_factory, pago_id)] == [
        ("PAY-1", "aplicado"), ("PAY-2", "a_reembolsar")]


async def test_re_entrega_del_mismo_pago_sobrante_es_idempotente(client, seed_ids, session_factory, pasarela) -> None:
    reserva, pago_id, _ = await _pago_mp(client, seed_ids, session_factory)
    await _acreditar(session_factory, pago_id, mp_payment_id="PAY-1", **OK)
    await _acreditar(session_factory, pago_id, mp_payment_id="PAY-2", **OK)
    assert (await _acreditar(session_factory, pago_id, mp_payment_id="PAY-2", **OK)).efecto == "sin_cambios"
    assert (await _acreditar(session_factory, pago_id, mp_payment_id="PAY-1", **OK)).efecto == "sin_cambios"
    assert len(await _aprobaciones(session_factory, pago_id)) == 2
    async with session_factory() as s:
        auditorias = (await s.execute(select(RegistroAuditoria).where(
            RegistroAuditoria.datos_despues["origen"].astext == "sena_pago_excedente"))).scalars().all()
    assert len(auditorias) == 1


async def test_el_pago_en_revision_acreditado_despues_no_pierde_el_pago_discrepante(
        client, seed_ids, session_factory, pasarela) -> None:
    reserva, pago_id, _ = await _pago_mp(client, seed_ids, session_factory)
    assert (await _acreditar(session_factory, pago_id, mp_payment_id="PAY-1",
                             monto_reportado=Decimal("100.00"), moneda_reportada="ARS")).efecto == "en_revision"
    assert (await _acreditar(session_factory, pago_id, mp_payment_id="PAY-2", **OK)).efecto == "acreditado"
    (pago,) = await pagos_de(session_factory, reserva["turno_id"])
    assert pago.mp_payment_id == "PAY-2"
    filas = {a.mp_payment_id: a for a in await _aprobaciones(session_factory, pago_id)}
    assert (filas["PAY-1"].estado, filas["PAY-1"].monto_reportado) == ("a_reembolsar", Decimal("100.00"))
    assert filas["PAY-2"].estado == "aplicado"


async def test_pago_aprobado_con_el_turno_no_vigente_se_registra_a_reembolsar(
        client, seed_ids, session_factory, pasarela) -> None:
    reserva, pago_id, _ = await _pago_mp(client, seed_ids, session_factory)
    await forzar_vencimiento(session_factory, reserva["turno_id"], datetime.now(timezone.utc) - timedelta(minutes=1))
    assert (await _acreditar(session_factory, pago_id, mp_payment_id="PAY-9", **OK)).efecto == "a_reembolsar"
    assert [(a.mp_payment_id, a.estado) for a in await _aprobaciones(session_factory, pago_id)] == [("PAY-9", "a_reembolsar")]


async def test_el_webhook_informa_a_reembolsar_para_un_segundo_pago_distinto(
        client, seed_ids, session_factory, pasarela) -> None:
    reserva, pago_id, ref = await _pago_mp(client, seed_ids, session_factory)

    async def enviar(dato: str):
        ts = str(int(time.time() * 1000))
        cab = {"x-signature": f"ts={ts},v1={calcular_firma(SECRETO_WEBHOOK, dato, 'req-1', ts)}", "x-request-id": "req-1"}
        return await client.post("/api/webhooks/mercadopago", params={"data.id": dato, "type": "payment"},
                                 headers=cab, json={"type": "payment", "data": {"id": dato}})

    assert (await enviar(f"fake-approved-{ref}@3000.00@ARS")).json()["status"] == "acreditado"
    assert (await enviar(f"fake-approved-{ref}@3000.00@ARS")).json()["status"] == "sin_cambios"
    assert (await enviar(f"fake-approved-{ref}@3000.0@ARS")).json()["status"] == "a_reembolsar"  # otro id de pago


# --- Hallazgo 3: un deadlock no es un conflicto de agenda -------------------------------------------------

def _error_pg(sqlstate: str) -> DBAPIError:
    class Orig(Exception):
        pass

    orig = Orig(sqlstate)
    orig.sqlstate = sqlstate  # type: ignore[attr-defined]
    return DBAPIError("sentencia", {}, orig)


async def test_deadlocks_agotados_no_terminan_en_reembolso_sino_en_error_reintentable(
        client, seed_ids, session_factory, pasarela, monkeypatch) -> None:
    reserva, pago_id, _ = await _pago_mp(client, seed_ids, session_factory)
    original = svc._acreditar_una_vez
    forzados: list[bool] = []

    async def con_deadlock(session, pid, **kw):
        forzados.append(kw["forzar_conflicto"])
        if not kw["forzar_conflicto"]:
            raise _error_pg("40P01")
        return await original(session, pid, **kw)  # el bug: el último intento fuerza un reembolso

    monkeypatch.setattr(svc, "_acreditar_una_vez", con_deadlock)
    with pytest.raises(OperacionReintentableError):
        await _acreditar(session_factory, pago_id, mp_payment_id="PAY-1", **OK)
    assert not any(forzados)
    (pago,) = await pagos_de(session_factory, reserva["turno_id"])
    assert pago.estado == "pendiente" and (await turno_de(session_factory, reserva["turno_id"])).estado == "en_espera"


async def test_un_deadlock_pasajero_se_reintenta_y_acredita(client, seed_ids, session_factory, pasarela, monkeypatch) -> None:
    reserva, pago_id, _ = await _pago_mp(client, seed_ids, session_factory)
    original = svc._acreditar_una_vez
    llamadas = 0

    async def una_vez_deadlock(session, pid, **kw):
        nonlocal llamadas
        llamadas += 1
        if llamadas == 1:
            raise _error_pg("40P01")
        return await original(session, pid, **kw)

    monkeypatch.setattr(svc, "_acreditar_una_vez", una_vez_deadlock)
    assert (await _acreditar(session_factory, pago_id, mp_payment_id="PAY-1", **OK)).efecto == "acreditado"
    assert llamadas == 2


async def test_un_conflicto_real_de_agenda_23p01_sigue_terminando_en_reembolso(
        client, seed_ids, session_factory, pasarela, monkeypatch) -> None:
    reserva, pago_id, _ = await _pago_mp(client, seed_ids, session_factory)
    original = svc._acreditar_una_vez

    async def siempre_23p01(session, pid, **kw):
        if not kw["forzar_conflicto"]:
            raise _error_pg("23P01")
        return await original(session, pid, **kw)

    monkeypatch.setattr(svc, "_acreditar_una_vez", siempre_23p01)
    assert (await _acreditar(session_factory, pago_id, mp_payment_id="PAY-1", **OK)).efecto == "a_reembolsar"
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "cancelado"


async def test_el_webhook_responde_503_si_la_acreditacion_agota_los_reintentos(
        client, seed_ids, session_factory, pasarela, monkeypatch) -> None:
    reserva, pago_id, ref = await _pago_mp(client, seed_ids, session_factory)

    async def deadlock(session, pid, **kw):
        raise _error_pg("40P01")

    monkeypatch.setattr(svc, "_acreditar_una_vez", deadlock)
    dato = f"fake-approved-{ref}@3000.00@ARS"
    ts = str(int(time.time() * 1000))
    cab = {"x-signature": f"ts={ts},v1={calcular_firma(SECRETO_WEBHOOK, dato, 'req-1', ts)}", "x-request-id": "req-1"}
    r = await client.post("/api/webhooks/mercadopago", params={"data.id": dato, "type": "payment"}, headers=cab,
                          json={"type": "payment", "data": {"id": dato}})
    assert r.status_code == 503  # Mercado Pago reintenta más tarde; nunca un reembolso
    assert (await pagos_de(session_factory, reserva["turno_id"]))[0].estado == "pendiente"


# --- Hallazgo 4: mismo orden de locks en todos los caminos ---------------------------------------------------

class _Sentencias:
    def __init__(self, session_factory) -> None:
        self.engine = session_factory.kw["bind"].sync_engine
        self.sql: list[str] = []

    def __enter__(self):
        event.listen(self.engine, "before_cursor_execute", self._capturar)
        return self

    def __exit__(self, *a):
        event.remove(self.engine, "before_cursor_execute", self._capturar)

    def _capturar(self, conn, cursor, statement, params, context, executemany):
        self.sql.append(statement)

    def indice(self, *trozos: str) -> int:
        for i, s in enumerate(self.sql):
            if all(t in s for t in trozos):
                return i
        return -1


def _orden_correcto(c: _Sentencias) -> None:
    advisory = c.indice("pg_advisory_xact_lock")
    turno = c.indice("FROM turno", "FOR UPDATE")
    pago = c.indice("FROM pago_sena", "FOR UPDATE")
    assert advisory >= 0 and turno >= 0, c.sql
    assert advisory < turno
    assert pago == -1 or turno < pago, c.sql


async def test_acreditar_toma_advisory_luego_turno_luego_pago(client, seed_ids, session_factory, pasarela) -> None:
    _, pago_id, _ = await _pago_mp(client, seed_ids, session_factory)
    with _Sentencias(session_factory) as c:
        await _acreditar(session_factory, pago_id, mp_payment_id="PAY-1", **OK)
    _orden_correcto(c)
    assert c.indice("FROM pago_sena", "FOR UPDATE") >= 0


async def test_cambiar_estado_toma_advisory_luego_turno_luego_pago(client, seed_ids, session_factory, pasarela) -> None:
    reserva, pago_id, _ = await _pago_mp(client, seed_ids, session_factory)
    await _acreditar(session_factory, pago_id, mp_payment_id="PAY-1", **OK)
    with _Sentencias(session_factory) as c:
        async with session_factory() as s:
            await cambiar_estado_turno(s, reserva["turno_id"], "confirmado", None)
    _orden_correcto(c)
    assert c.indice("FROM pago_sena", "FOR UPDATE") >= 0


async def test_el_barrido_toma_advisory_luego_turno_luego_pago(client, seed_ids, session_factory, pasarela) -> None:
    from app.pagos.barrido import expirar_pre_reservas
    reserva, _, _ = await _pago_mp(client, seed_ids, session_factory)
    await forzar_vencimiento(session_factory, reserva["turno_id"], datetime.now(timezone.utc) - timedelta(minutes=1))
    with _Sentencias(session_factory) as c:
        async with session_factory() as s:
            assert await expirar_pre_reservas(s, datetime.now(timezone.utc)) == 1
    _orden_correcto(c)


async def test_cambiar_estado_reintenta_un_deadlock_y_no_filtra_un_500(
        client, seed_ids, session_factory, pasarela, monkeypatch) -> None:
    reserva, pago_id, _ = await _pago_mp(client, seed_ids, session_factory)
    await _acreditar(session_factory, pago_id, mp_payment_id="PAY-1", **OK)
    original = svc._cambiar_estado_una_vez
    llamadas = 0

    async def una_vez(*a, **kw):
        nonlocal llamadas
        llamadas += 1
        if llamadas == 1:
            raise _error_pg("40P01")
        return await original(*a, **kw)

    monkeypatch.setattr(svc, "_cambiar_estado_una_vez", una_vez)
    async with session_factory() as s:
        assert (await cambiar_estado_turno(s, reserva["turno_id"], "confirmado", None)).estado_turno == "confirmado"

    async def siempre(*a, **kw):
        raise _error_pg("40P01")

    monkeypatch.setattr(svc, "_cambiar_estado_una_vez", siempre)
    async with session_factory() as s:
        with pytest.raises(OperacionReintentableError):
            await cambiar_estado_turno(s, reserva["turno_id"], "atendido", None)


async def test_acreditar_y_cambiar_estado_concurrentes_no_dan_error(client, seed_ids, session_factory, pasarela) -> None:
    for _ in range(3):
        reserva, pago_id, _ = await _pago_mp(client, seed_ids, session_factory)
        async with session_factory() as s:
            await s.execute(update(PagoSena).where(PagoSena.id == pago_id).values(estado="pendiente"))
            await s.commit()

        async def cancelar():
            async with session_factory() as s:
                try:
                    await cambiar_estado_turno(s, reserva["turno_id"], "cancelado", None)
                except Exception as exc:  # transiciones inválidas son válidas según quién gane
                    return type(exc).__name__
                return "ok"

        resultados = await asyncio.gather(
            _acreditar(session_factory, pago_id, mp_payment_id=f"PAY-{time.time_ns()}", **OK), cancelar(),
            return_exceptions=True)
        assert not any(isinstance(r, DBAPIError) for r in resultados), resultados
        async with session_factory() as s:  # limpia para la próxima vuelta (misma agenda)
            from app.pagos.models import AprobacionPago as A
            await s.execute(A.__table__.delete())
            await s.execute(PagoSena.__table__.delete())
            from app.turnos.models import Turno
            await s.execute(Turno.__table__.delete())
            await s.commit()


# --- Hallazgo 7: cabecera de firma malformada -> 401, nunca 500 ---------------------------------------------

@pytest.mark.parametrize("ts", ["²", "٣٤٥", "9" * 400, "1" * 30, "１２３", "-5", "1e9", ""])
def test_ts_no_ascii_o_desmedido_se_rechaza_sin_excepcion(ts: str) -> None:
    firma = "a" * 64
    ahora = datetime.now(timezone.utc)
    assert verificar_firma(secreto="s", x_signature=f"ts={ts},v1={firma}", x_request_id="r", data_id="1",
                           ahora=ahora, tolerancia_segundos=300) is False


@pytest.mark.parametrize("ts", ["²", "9" * 400, "1" * 30])
async def test_el_webhook_con_ts_malformado_responde_401(client, seed_ids, session_factory, pasarela, ts) -> None:
    r = await client.post("/api/webhooks/mercadopago", params={"data.id": "123", "type": "payment"},
                          headers={"x-signature": f"ts={ts},v1={'b' * 64}".encode("latin-1"), "x-request-id": "r"},  # bytes: '²' viaja en latin-1
                          json={"type": "payment", "data": {"id": "123"}})
    assert r.status_code == 401


# --- Hallazgo 8: la validación de la acreditación manual va bajo el lock -----------------------------------------

async def test_acreditacion_manual_con_lectura_vieja_de_una_transferencia_ya_vencida_se_rechaza(
        client, seed_ids, session_factory, pasarela) -> None:
    f = fecha_laboral()
    await sembrar_agenda(session_factory, seed_ids, f)
    await configurar_transferencia(session_factory)
    reserva = await reservar(client, seed_ids, local(f, "10:00"))
    pago_tr = (await iniciar(client, reserva, "transferencia")).json()["pago_id"]

    async with session_factory() as s_admin:
        leido = await s_admin.get(PagoSena, pago_tr)  # el admin ya había leído el pago como pendiente (referencia fuerte: el identity map es débil)
        assert leido is not None and leido.estado == "pendiente"
        assert (await iniciar(client, reserva, "mercadopago")).status_code == 201  # el paciente cambia a MP
        with pytest.raises(PagoNoAcreditableError) as exc:
            await acreditar_transferencia(s_admin, pago_tr, usuario_id=1)
        assert exc.value.motivo == "pago_no_pendiente"
    pagos = await pagos_de(session_factory, reserva["turno_id"])
    assert [(p.medio, p.estado) for p in pagos] == [("transferencia", "vencido"), ("mercadopago", "pendiente")]
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "en_espera"


async def test_acreditacion_manual_con_el_turno_vencido_bajo_lock_se_rechaza(
        client, seed_ids, session_factory, pasarela) -> None:
    f = fecha_laboral()
    await sembrar_agenda(session_factory, seed_ids, f)
    await configurar_transferencia(session_factory)
    reserva = await reservar(client, seed_ids, local(f, "10:00"))
    pago_tr = (await iniciar(client, reserva, "transferencia")).json()["pago_id"]
    async with session_factory() as s_admin:
        leido = await s_admin.get(PagoSena, pago_tr)
        assert leido is not None
        await forzar_vencimiento(session_factory, reserva["turno_id"], datetime.now(timezone.utc) - timedelta(minutes=1))
        with pytest.raises(PagoNoAcreditableError) as exc:
            await acreditar_transferencia(s_admin, pago_tr, usuario_id=1)
        assert exc.value.motivo == "vencido"
    assert (await pagos_de(session_factory, reserva["turno_id"]))[0].estado == "pendiente"
