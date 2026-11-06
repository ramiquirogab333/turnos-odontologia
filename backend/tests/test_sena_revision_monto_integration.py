"""C-06 (14.x, RN-SN-09): el monto informado por la pasarela debe coincidir con la seña; si no, queda en revisión."""

import logging
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from app.models.core import RegistroAuditoria
from app.pagos.pasarela import PagoPasarela, PasarelaNoDisponibleError, calcular_firma
from tests.sena_helpers import (
    SECRETO_WEBHOOK, TELEFONO, fecha_laboral, forzar_vencimiento, iniciar, local, pagos_de, reservar,
    sembrar_agenda, turno_de,
)
from tests.test_sena_admin_integration import _usuario

URL = "/api/webhooks/mercadopago"


def _firmado(data_id: str) -> dict[str, str]:
    ts = str(int(time.time() * 1000))
    return {"x-signature": f"ts={ts},v1={calcular_firma(SECRETO_WEBHOOK, data_id, 'req-sint-0001', ts)}",
            "x-request-id": "req-sint-0001"}


async def _enviar(client, data_id: str):
    # (acá los ids se arman a propósito, con o sin monto y moneda)
    return await client.post(URL, params={"data.id": data_id, "type": "payment"}, headers=_firmado(data_id),
                             json={"type": "payment", "data": {"id": data_id}})


async def _con_pago(client, ids, factory, hhmm="10:00"):
    f = fecha_laboral()
    await sembrar_agenda(factory, ids, f)  # seña esperada: 3000.00
    reserva = await reservar(client, ids, local(f, hhmm))
    r = await iniciar(client, reserva, "mercadopago")
    return reserva, r.json()["referencia_externa"]


async def _auditoria_revision(factory, pago_id):
    async with factory() as s:
        return list((await s.execute(select(RegistroAuditoria).where(
            RegistroAuditoria.entidad == "pago_sena", RegistroAuditoria.entidad_id == str(pago_id),
            RegistroAuditoria.datos_despues["origen"].astext == "sena_en_revision"))).scalars().all())


async def test_monto_exacto_acredita(client, seed_ids, session_factory, pasarela) -> None:
    reserva, ref = await _con_pago(client, seed_ids, session_factory)
    r = await _enviar(client, f"fake-approved-{ref}@3000.00@ARS")
    assert r.status_code == 200 and r.json()["status"] == "acreditado"
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "reservado"
    (pago,) = await pagos_de(session_factory, reserva["turno_id"])
    assert pago.estado == "acreditado" and pago.monto_reportado is None


async def test_monto_equivalente_con_otra_escala_decimal_acredita(client, seed_ids, session_factory, pasarela) -> None:
    reserva, ref = await _con_pago(client, seed_ids, session_factory)
    assert (await _enviar(client, f"fake-approved-{ref}@3000@ARS")).json()["status"] == "acreditado"


async def test_monto_menor_no_acredita_y_queda_en_revision(client, seed_ids, session_factory, pasarela) -> None:
    reserva, ref = await _con_pago(client, seed_ids, session_factory)
    r = await _enviar(client, f"fake-approved-{ref}@2999.99@ARS")
    assert r.status_code == 200 and r.json()["status"] == "en_revision"
    turno = await turno_de(session_factory, reserva["turno_id"])
    assert turno.estado == "en_espera" and turno.en_espera_vence_en is not None  # sigue su vencimiento normal
    (pago,) = await pagos_de(session_factory, reserva["turno_id"])
    assert pago.estado == "en_revision" and pago.monto == Decimal("3000.00")
    assert pago.monto_reportado == Decimal("2999.99") and pago.mp_payment_id == f"fake-approved-{ref}@2999.99@ARS"
    (aud,) = await _auditoria_revision(session_factory, pago.id)
    assert aud.datos_despues["monto_esperado"] == "3000.00" and aud.datos_despues["monto_reportado"] == "2999.99"
    assert "Carlos" not in str(aud.datos_despues) and TELEFONO not in str(aud.datos_despues)


async def test_monto_mayor_tampoco_acredita(client, seed_ids, session_factory, pasarela) -> None:
    reserva, ref = await _con_pago(client, seed_ids, session_factory)
    assert (await _enviar(client, f"fake-approved-{ref}@3000.01")).json()["status"] == "en_revision"
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "en_espera"
    (pago,) = await pagos_de(session_factory, reserva["turno_id"])
    assert pago.estado == "en_revision" and pago.monto_reportado == Decimal("3000.01")


async def test_moneda_distinta_de_ars_queda_en_revision(client, seed_ids, session_factory, pasarela) -> None:
    reserva, ref = await _con_pago(client, seed_ids, session_factory)
    assert (await _enviar(client, f"fake-approved-{ref}@3000.00@USD")).json()["status"] == "en_revision"
    (pago,) = await pagos_de(session_factory, reserva["turno_id"])
    assert pago.estado == "en_revision" and pago.moneda_reportada == "USD"
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "en_espera"


async def test_webhook_duplicado_con_monto_distinto_es_idempotente(client, seed_ids, session_factory, pasarela) -> None:
    reserva, ref = await _con_pago(client, seed_ids, session_factory)
    dato = f"fake-approved-{ref}@100.00@ARS"
    assert (await _enviar(client, dato)).json()["status"] == "en_revision"
    segundo = await _enviar(client, dato)
    assert segundo.status_code == 200 and segundo.json()["status"] == "sin_cambios"
    (pago,) = await pagos_de(session_factory, reserva["turno_id"])
    assert len(await _auditoria_revision(session_factory, pago.id)) == 1


async def test_reentrega_con_el_monto_correcto_acredita_un_pago_en_revision(
        client, seed_ids, session_factory, pasarela) -> None:
    reserva, ref = await _con_pago(client, seed_ids, session_factory)
    assert (await _enviar(client, f"fake-approved-{ref}@100.00")).json()["status"] == "en_revision"
    assert (await _enviar(client, f"fake-approved-{ref}@3000.00@ARS")).json()["status"] == "acreditado"
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "reservado"


async def test_recepcion_acredita_a_mano_un_pago_de_mp_en_revision(client, seed_ids, session_factory, pasarela) -> None:
    uid, auth = await _usuario(session_factory, client, "recepcion")
    reserva, ref = await _con_pago(client, seed_ids, session_factory)
    await _enviar(client, f"fake-approved-{ref}@100.00")
    (pago,) = await pagos_de(session_factory, reserva["turno_id"])
    r = await client.post(f"/api/admin/pagos-sena/{pago.id}/acreditar", headers=auth)
    assert r.status_code == 200 and r.json()["estado_pago"] == "acreditado"
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "reservado"
    (pago,) = await pagos_de(session_factory, reserva["turno_id"])
    assert pago.acreditado_por_usuario_id == uid


async def test_en_revision_sobre_un_turno_vencido_se_resuelve_a_reembolsar(
        client, seed_ids, session_factory, pasarela) -> None:
    _, auth = await _usuario(session_factory, client, "admin")
    reserva, ref = await _con_pago(client, seed_ids, session_factory)
    await _enviar(client, f"fake-approved-{ref}@100.00")
    await forzar_vencimiento(session_factory, reserva["turno_id"], datetime.now(timezone.utc) - timedelta(minutes=1))
    (pago,) = await pagos_de(session_factory, reserva["turno_id"])
    r = await client.post(f"/api/admin/pagos-sena/{pago.id}/acreditar", headers=auth)
    assert r.status_code == 200 and r.json()["estado_pago"] == "a_reembolsar"
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "cancelado"


async def test_el_barrido_cancela_el_turno_pero_no_pisa_un_pago_en_revision(
        client, seed_ids, session_factory, pasarela) -> None:
    from app.pagos.barrido import expirar_pre_reservas
    reserva, ref = await _con_pago(client, seed_ids, session_factory)
    await _enviar(client, f"fake-approved-{ref}@100.00")
    await forzar_vencimiento(session_factory, reserva["turno_id"], datetime.now(timezone.utc) - timedelta(minutes=1))
    async with session_factory() as s:
        assert await expirar_pre_reservas(s, datetime.now(timezone.utc)) == 1
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "cancelado"
    assert (await pagos_de(session_factory, reserva["turno_id"]))[0].estado == "en_revision"  # dinero a resolver a mano


async def test_el_log_no_filtra_pii_ni_secretos(client, seed_ids, session_factory, pasarela, caplog) -> None:
    _, ref = await _con_pago(client, seed_ids, session_factory)
    with caplog.at_level(logging.INFO):
        await _enviar(client, f"fake-approved-{ref}@1.00")
    assert "Carlos" not in caplog.text and TELEFONO not in caplog.text and SECRETO_WEBHOOK not in caplog.text


async def test_pasarela_falsa_sin_monto_codificado_tambien_va_a_revision(client, seed_ids, session_factory, pasarela) -> None:
    """Fail closed: sin monto informado no se puede verificar, aunque sea la pasarela falsa."""
    reserva, ref = await _con_pago(client, seed_ids, session_factory)
    assert (await _enviar(client, f"fake-approved-{ref}")).json()["status"] == "en_revision"
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "en_espera"


# --- Fail closed con el adaptador REAL de Mercado Pago (httpx.MockTransport, sin red) -------------------

def _mp_real(cuerpo: dict):
    import httpx
    from app.main import app
    from app.pagos.deps import get_pasarela
    from app.pagos.mercadopago import MercadoPagoPasarela

    mp = MercadoPagoPasarela(
        access_token="token-sintetico-tests", api_base_url="https://mp.example.test",
        public_base_url="http://localhost:5173", api_public_base_url="http://localhost:8000",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=cuerpo)))
    app.dependency_overrides[get_pasarela] = lambda: mp


def _pago_mp(ref: str, **extra) -> dict:
    return {"id": 98765, "status": "approved", "external_reference": ref, **extra}


async def _con_mp_real(client, ids, factory, cuerpo_extra: dict):
    from app.main import app
    from app.pagos.deps import get_pasarela
    reserva, ref = await _con_pago(client, ids, factory)
    _mp_real(_pago_mp(ref, **cuerpo_extra))
    return reserva, app, get_pasarela


async def test_mp_real_sin_transaction_amount_va_a_revision(client, seed_ids, session_factory, pasarela) -> None:
    reserva, app, g = await _con_mp_real(client, seed_ids, session_factory, {"currency_id": "ARS"})
    try:
        r = await _enviar(client, "98765")
    finally:
        app.dependency_overrides.pop(g, None)
    assert r.status_code == 200 and r.json()["status"] == "en_revision"
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "en_espera"
    (pago,) = await pagos_de(session_factory, reserva["turno_id"])
    assert pago.estado == "en_revision" and pago.monto_reportado is None and pago.moneda_reportada == "ARS"
    (aud,) = await _auditoria_revision(session_factory, pago.id)
    assert aud.datos_despues["monto_reportado"] is None and "Carlos" not in str(aud.datos_despues)


async def test_mp_real_sin_currency_id_va_a_revision(client, seed_ids, session_factory, pasarela) -> None:
    reserva, app, g = await _con_mp_real(client, seed_ids, session_factory, {"transaction_amount": 3000.0})
    try:
        r = await _enviar(client, "98765")
    finally:
        app.dependency_overrides.pop(g, None)
    assert r.json()["status"] == "en_revision"
    (pago,) = await pagos_de(session_factory, reserva["turno_id"])
    assert pago.estado == "en_revision" and pago.monto_reportado == Decimal("3000.00") and pago.moneda_reportada is None


async def test_mp_real_con_monto_ilegible_va_a_revision(client, seed_ids, session_factory, pasarela) -> None:
    reserva, app, g = await _con_mp_real(
        client, seed_ids, session_factory, {"transaction_amount": "no-es-un-numero", "currency_id": "ARS"})
    try:
        r = await _enviar(client, "98765")
    finally:
        app.dependency_overrides.pop(g, None)
    assert r.status_code == 200 and r.json()["status"] == "en_revision"


async def test_mp_real_con_monto_y_moneda_correctos_acredita(client, seed_ids, session_factory, pasarela) -> None:
    reserva, app, g = await _con_mp_real(
        client, seed_ids, session_factory, {"transaction_amount": 3000.0, "currency_id": "ARS"})
    try:
        r = await _enviar(client, "98765")
    finally:
        app.dependency_overrides.pop(g, None)
    assert r.json()["status"] == "acreditado"
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "reservado"


async def test_mp_real_sin_monto_reentrega_es_idempotente(client, seed_ids, session_factory, pasarela) -> None:
    reserva, app, g = await _con_mp_real(client, seed_ids, session_factory, {"currency_id": "ARS"})
    try:
        primero = await _enviar(client, "98765")
        segundo = await _enviar(client, "98765")
    finally:
        app.dependency_overrides.pop(g, None)
    assert (primero.json()["status"], segundo.json()["status"]) == ("en_revision", "sin_cambios")
    (pago,) = await pagos_de(session_factory, reserva["turno_id"])
    assert len(await _auditoria_revision(session_factory, pago.id)) == 1


async def test_la_acreditacion_manual_no_necesita_datos_de_la_pasarela(client, seed_ids, session_factory, pasarela) -> None:
    """El camino manual (recepción/admin) no tiene datos de pasarela y no se ve afectado por el fail closed."""
    _, auth = await _usuario(session_factory, client, "recepcion")
    f = fecha_laboral()
    await sembrar_agenda(session_factory, seed_ids, f)
    reserva = await reservar(client, seed_ids, local(f, "11:00"))
    from tests.sena_helpers import configurar_transferencia
    await configurar_transferencia(session_factory)
    pago_id = (await iniciar(client, reserva, "transferencia")).json()["pago_id"]
    r = await client.post(f"/api/admin/pagos-sena/{pago_id}/acreditar", headers=auth)
    assert r.status_code == 200 and r.json()["estado_pago"] == "acreditado"


def test_el_pago_de_la_pasarela_lleva_monto_y_moneda() -> None:
    p = PagoPasarela(id="1", estado="approved", referencia_externa="r", monto=Decimal("1.00"), moneda="ARS")
    assert (p.monto, p.moneda) == (Decimal("1.00"), "ARS")
    assert issubclass(PasarelaNoDisponibleError, Exception)
