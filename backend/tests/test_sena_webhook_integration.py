"""C-06 (7.1): webhook POST /api/webhooks/mercadopago con firma HMAC. Secreto sintético y pasarela falsa (sin red)."""

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.core import RegistroAuditoria
from app.pagos.pasarela import calcular_firma
from tests.sena_helpers import (
    SECRETO_WEBHOOK, TELEFONO, fecha_laboral, forzar_vencimiento, iniciar, local, pagos_de, reservar,
    sembrar_agenda, turno_de,
)

URL = "/api/webhooks/mercadopago"


def _firmado(data_id: str, *, secreto: str = SECRETO_WEBHOOK, ts_ms: int | None = None,
             request_id: str = "req-sintetico-0001") -> dict[str, str]:
    ts = str(ts_ms if ts_ms is not None else int(time.time() * 1000))
    return {"x-signature": f"ts={ts},v1={calcular_firma(secreto, data_id, request_id, ts)}",
            "x-request-id": request_id}


async def _enviar(client, data_id: str, headers: dict[str, str] | None = None, tipo: str = "payment"):
    if "@" not in data_id and data_id.startswith("fake-"):
        data_id += "@3000.00@ARS"  # la pasarela falsa informa monto y moneda; la seña de estos tests es 3000.00
    cab = _firmado(data_id) if headers is None else headers
    return await client.post(URL, params={"data.id": data_id, "type": tipo}, headers=cab,
                             json={"type": tipo, "data": {"id": data_id}})


async def _con_pago_pendiente(client, ids, factory, hhmm="10:00"):
    f = fecha_laboral()
    await sembrar_agenda(factory, ids, f)
    reserva = await reservar(client, ids, local(f, hhmm))
    r = await iniciar(client, reserva, "mercadopago")
    return reserva, r.json()["referencia_externa"]


async def _auditorias_de_acreditacion(factory, turno_id):
    async with factory() as s:
        filas = await s.execute(select(RegistroAuditoria).where(
            RegistroAuditoria.entidad == "turno", RegistroAuditoria.entidad_id == str(turno_id),
            RegistroAuditoria.datos_despues["origen"].astext == "acreditacion_sena"))
        return list(filas.scalars().all())


async def test_firma_valida_y_pago_aprobado_acredita_y_reserva(client, seed_ids, session_factory, pasarela) -> None:
    reserva, ref = await _con_pago_pendiente(client, seed_ids, session_factory)
    pago_mp = f"fake-approved-{ref}@3000.00@ARS"
    r = await _enviar(client, pago_mp)
    assert r.status_code == 200, r.text
    assert pasarela.consultas == [pago_mp]
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "reservado"
    (pago,) = await pagos_de(session_factory, reserva["turno_id"])
    assert pago.estado == "acreditado" and pago.mp_payment_id == pago_mp
    assert pago.acreditado_por_usuario_id is None  # lo acreditó la pasarela, no una persona


async def test_firma_invalida_ausente_o_con_ts_vencido_es_401_sin_consultar_la_pasarela(
        client, seed_ids, session_factory, pasarela) -> None:
    reserva, ref = await _con_pago_pendiente(client, seed_ids, session_factory)
    pago_mp = f"fake-approved-{ref}"
    hace_una_hora = int((time.time() - 3600) * 1000)
    for cabeceras in (
        _firmado(pago_mp, secreto="otro-secreto-sintetico"),   # calculada con otro secreto
        {"x-request-id": "req-sintetico-0001"},                 # sin x-signature
        {"x-signature": "basura", "x-request-id": "req-sintetico-0001"},
        _firmado(pago_mp, ts_ms=hace_una_hora),                 # firma correcta pero fuera de tolerancia
        {"x-signature": _firmado(pago_mp)["x-signature"]},      # sin x-request-id
    ):
        r = await _enviar(client, pago_mp, headers=cabeceras)
        assert r.status_code == 401, (cabeceras, r.text)
    assert pasarela.consultas == []
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "en_espera"
    (pago,) = await pagos_de(session_factory, reserva["turno_id"])
    assert pago.estado == "pendiente"


async def test_sin_data_id_no_se_puede_verificar_y_es_401(client, seed_ids, session_factory, pasarela) -> None:
    r = await client.post(URL, headers=_firmado("123"), json={"type": "payment"})
    assert r.status_code == 401 and pasarela.consultas == []


async def test_webhook_duplicado_es_200_idempotente_con_una_sola_auditoria(
        client, seed_ids, session_factory, pasarela) -> None:
    reserva, ref = await _con_pago_pendiente(client, seed_ids, session_factory)
    pago_mp = f"fake-approved-{ref}"
    assert (await _enviar(client, pago_mp)).status_code == 200
    assert (await _enviar(client, pago_mp)).status_code == 200
    assert len(await _auditorias_de_acreditacion(session_factory, reserva["turno_id"])) == 1
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "reservado"


async def test_dos_webhooks_simultaneos_producen_un_solo_efecto(client, seed_ids, session_factory, pasarela) -> None:
    reserva, ref = await _con_pago_pendiente(client, seed_ids, session_factory)
    pago_mp = f"fake-approved-{ref}"
    a, b = await asyncio.gather(_enviar(client, pago_mp), _enviar(client, pago_mp))
    assert (a.status_code, b.status_code) == (200, 200)
    assert len(await _auditorias_de_acreditacion(session_factory, reserva["turno_id"])) == 1
    (pago,) = await pagos_de(session_factory, reserva["turno_id"])
    assert pago.estado == "acreditado"


async def test_pago_rechazado_o_referencia_desconocida_es_200_sin_cambios_y_log_sin_pii(
        client, seed_ids, session_factory, pasarela, caplog) -> None:
    reserva, ref = await _con_pago_pendiente(client, seed_ids, session_factory)
    with caplog.at_level(logging.INFO):
        rechazado = await _enviar(client, f"fake-rejected-{ref}")
        desconocido = await _enviar(client, "fake-approved-referencia-que-no-existe")
        inexistente = await _enviar(client, "999999")  # id que la pasarela no conoce
    assert (rechazado.status_code, desconocido.status_code, inexistente.status_code) == (200, 200, 200)
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "en_espera"
    (pago,) = await pagos_de(session_factory, reserva["turno_id"])
    assert pago.estado == "pendiente"
    assert "Carlos" not in caplog.text and TELEFONO not in caplog.text and SECRETO_WEBHOOK not in caplog.text
    assert "rejected" in caplog.text  # el evento queda registrado (solo referencia y estado)


async def test_tipo_distinto_de_payment_es_200_ignorado_sin_consultar(client, seed_ids, session_factory, pasarela) -> None:
    reserva, ref = await _con_pago_pendiente(client, seed_ids, session_factory)
    r = await _enviar(client, f"fake-approved-{ref}", tipo="merchant_order")
    assert r.status_code == 200 and pasarela.consultas == []
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "en_espera"


async def test_pasarela_caida_al_consultar_es_503_para_que_mercado_pago_reintente(
        client, seed_ids, session_factory, pasarela) -> None:
    reserva, ref = await _con_pago_pendiente(client, seed_ids, session_factory)
    pasarela.falla_obtener = True
    r = await _enviar(client, f"fake-approved-{ref}")
    assert r.status_code == 503
    pasarela.falla_obtener = False
    assert (await _enviar(client, f"fake-approved-{ref}")).status_code == 200  # el reintento acredita
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "reservado"


async def test_pago_tardio_sobre_turno_vencido_queda_a_reembolsar_y_responde_200(
        client, seed_ids, session_factory, pasarela) -> None:
    reserva, ref = await _con_pago_pendiente(client, seed_ids, session_factory)
    await forzar_vencimiento(session_factory, reserva["turno_id"], datetime.now(timezone.utc) - timedelta(minutes=1))
    r = await _enviar(client, f"fake-approved-{ref}")
    assert r.status_code == 200
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "cancelado"
    (pago,) = await pagos_de(session_factory, reserva["turno_id"])
    assert pago.estado == "a_reembolsar"


async def test_sin_secreto_configurado_el_webhook_falla_cerrado(
        client, seed_ids, session_factory, pasarela, monkeypatch) -> None:
    monkeypatch.delenv("MP_WEBHOOK_SECRET")
    r = await _enviar(client, "fake-approved-cualquiera-0001")
    assert r.status_code == 503 and pasarela.consultas == []
