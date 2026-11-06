"""C-06 (3.2/3.3): adaptadores de pasarela. El falso sin estado; el real con httpx.MockTransport (sin red)."""

import json
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest

from app.pagos.fake import FakePasarela
from app.pagos.mercadopago import MercadoPagoPasarela
from app.pagos.pasarela import PagoInexistenteError, PasarelaNoDisponibleError

VENCE = datetime(2031, 3, 3, 13, 0, tzinfo=timezone(timedelta(hours=-3)))
TOKEN = "APP_USR-token-sintetico-que-no-debe-filtrarse"
PUBLIC = "https://clinica.example.test"
API = "https://api.clinica.example.test"


# --- Adaptador falso ----------------------------------------------------------------------

async def test_fake_crear_preferencia_vuelve_al_front_con_el_turno() -> None:
    pref = await FakePasarela(PUBLIC).crear_preferencia(
        turno_id=42, referencia_externa="ref-sintetica-0001", monto=Decimal("3000.00"),
        descripcion="Seña turno", vence_en=VENCE)
    assert pref.checkout_url == f"{PUBLIC}/?pago=retorno&turno=42"


async def test_fake_obtener_pago_decodifica_estado_y_referencia() -> None:
    fake = FakePasarela(PUBLIC)
    ok = await fake.obtener_pago("fake-approved-ref-sintetica-0001")
    assert (ok.id, ok.estado, ok.referencia_externa) == ("fake-approved-ref-sintetica-0001", "approved", "ref-sintetica-0001")
    rechazado = await fake.obtener_pago("fake-rejected-abc123def456")
    assert (rechazado.estado, rechazado.referencia_externa) == ("rejected", "abc123def456")


async def test_fake_no_comparte_estado_entre_instancias() -> None:
    a = await FakePasarela(PUBLIC).obtener_pago("fake-approved-xyz-00000001")
    b = await FakePasarela("https://otra.example.test").obtener_pago("fake-approved-xyz-00000001")
    assert a == b


@pytest.mark.parametrize("pago_id", ["123456", "fake-", "fake-approved-", "otro-approved-x"])
async def test_fake_id_no_reconocido_es_inexistente(pago_id: str) -> None:
    with pytest.raises(PagoInexistenteError):
        await FakePasarela(PUBLIC).obtener_pago(pago_id)


# --- Adaptador de Mercado Pago ---------------------------------------------------------------

def _adaptador(handler: httpx.MockTransport) -> MercadoPagoPasarela:
    return MercadoPagoPasarela(access_token=TOKEN, api_base_url="https://mp.example.test",
                               public_base_url=PUBLIC, api_public_base_url=API, transport=handler)


async def test_crear_preferencia_arma_el_body_y_las_cabeceras() -> None:
    capturado: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capturado["req"] = request
        return httpx.Response(201, json={"id": "pref-1", "init_point": "https://mp.example.test/checkout/pref-1"})

    pref = await _adaptador(httpx.MockTransport(handler)).crear_preferencia(
        turno_id=42, referencia_externa="ref-sintetica-0001", monto=Decimal("3000.00"),
        descripcion="Seña turno Limpieza", vence_en=VENCE)

    req = capturado["req"]
    assert (req.method, str(req.url)) == ("POST", "https://mp.example.test/checkout/preferences")
    assert req.headers["Authorization"] == f"Bearer {TOKEN}"
    assert req.headers["X-Idempotency-Key"] == "ref-sintetica-0001"
    cuerpo = json.loads(req.content)
    assert cuerpo["external_reference"] == "ref-sintetica-0001"
    assert cuerpo["items"][0]["quantity"] == 1 and cuerpo["items"][0]["currency_id"] == "ARS"
    assert cuerpo["notification_url"] == f"{API}/api/webhooks/mercadopago"
    assert cuerpo["back_urls"] == {k: f"{PUBLIC}/?pago=retorno&turno=42" for k in ("success", "pending", "failure")}
    assert cuerpo["expires"] is True
    assert cuerpo["expiration_date_to"] == "2031-03-03T13:00:00.000-03:00"
    assert pref.checkout_url == "https://mp.example.test/checkout/pref-1" and pref.preferencia_id == "pref-1"


async def test_el_monto_viaja_exacto_sin_pasar_por_float() -> None:
    crudo: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        crudo.append(request.content)
        return httpx.Response(201, json={"id": "p", "init_point": "https://mp.example.test/c"})

    for monto in ("3000.00", "1000.10", "0.07"):
        await _adaptador(httpx.MockTransport(handler)).crear_preferencia(
            turno_id=1, referencia_externa="ref-sintetica-0001", monto=Decimal(monto),
            descripcion="Seña", vence_en=VENCE)
    assert [json.loads(c)["items"][0]["unit_price"] for c in crudo] == [3000.0, 1000.1, 0.07]
    assert b'"unit_price": 3000.00' in crudo[0] or b'"unit_price":3000.00' in crudo[0]
    assert b"1000.10" in crudo[1] and b"0.07" in crudo[2]


async def test_obtener_pago_parsea_la_respuesta() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET" and str(request.url) == "https://mp.example.test/v1/payments/987654"
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        return httpx.Response(200, json={"id": 987654, "status": "approved",
                                         "external_reference": "ref-sintetica-0001", "transaction_amount": 3000.0})

    pago = await _adaptador(httpx.MockTransport(handler)).obtener_pago("987654")
    assert (pago.id, pago.estado, pago.referencia_externa, pago.monto) == (
        "987654", "approved", "ref-sintetica-0001", Decimal("3000.0"))


async def test_obtener_pago_404_es_inexistente() -> None:
    adaptador = _adaptador(httpx.MockTransport(lambda r: httpx.Response(404, json={"message": "not found"})))
    with pytest.raises(PagoInexistenteError):
        await adaptador.obtener_pago("1")


@pytest.mark.parametrize("respuesta", [
    httpx.Response(500, text="boom"), httpx.Response(503, text="x"), httpx.Response(401, json={"message": "bad token"}),
])
async def test_5xx_y_rechazos_se_traducen_a_pasarela_no_disponible(respuesta: httpx.Response) -> None:
    adaptador = _adaptador(httpx.MockTransport(lambda r: respuesta))
    with pytest.raises(PasarelaNoDisponibleError):
        await adaptador.crear_preferencia(turno_id=1, referencia_externa="ref-sintetica-0001",
                                          monto=Decimal("10.00"), descripcion="Seña", vence_en=VENCE)
    with pytest.raises(PasarelaNoDisponibleError):
        await adaptador.obtener_pago("1")


async def test_timeout_se_traduce_a_pasarela_no_disponible() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    with pytest.raises(PasarelaNoDisponibleError):
        await _adaptador(httpx.MockTransport(handler)).obtener_pago("1")


async def test_el_token_no_aparece_en_logs_ni_excepciones(caplog: pytest.LogCaptureFixture) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("sin red", request=request)

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(PasarelaNoDisponibleError) as exc:
            await _adaptador(httpx.MockTransport(handler)).crear_preferencia(
                turno_id=1, referencia_externa="ref-sintetica-0001", monto=Decimal("10.00"),
                descripcion="Seña", vence_en=VENCE)
    assert TOKEN not in str(exc.value) and TOKEN not in repr(exc.value)
    assert TOKEN not in caplog.text
    assert TOKEN not in repr(_adaptador(httpx.MockTransport(handler)))


# --- RN-SN-09: monto y moneda informados --------------------------------------------------------

async def test_fake_decodifica_monto_y_moneda_del_id() -> None:
    p = await FakePasarela(PUBLIC).obtener_pago("fake-approved-ref-sintetica-0001@2999.99@USD")
    assert (p.referencia_externa, p.monto, p.moneda) == ("ref-sintetica-0001", Decimal("2999.99"), "USD")
    solo_monto = await FakePasarela(PUBLIC).obtener_pago("fake-approved-ref-sintetica-0001@10")
    assert (solo_monto.monto, solo_monto.moneda) == (Decimal("10"), None)
    sin = await FakePasarela(PUBLIC).obtener_pago("fake-approved-ref-sintetica-0001")
    assert (sin.monto, sin.moneda) == (None, None)


async def test_fake_monto_ilegible_es_inexistente() -> None:
    with pytest.raises(PagoInexistenteError):
        await FakePasarela(PUBLIC).obtener_pago("fake-approved-ref-sintetica-0001@abc")


async def test_mercadopago_parsea_la_moneda() -> None:
    adaptador = _adaptador(httpx.MockTransport(lambda r: httpx.Response(
        200, json={"id": 9, "status": "approved", "external_reference": "r", "transaction_amount": 3000.5,
                   "currency_id": "ARS"})))
    pago = await adaptador.obtener_pago("9")
    assert (pago.monto, pago.moneda) == (Decimal("3000.5"), "ARS")


@pytest.mark.parametrize("cuerpo,monto,moneda", [
    ({"id": 9, "status": "approved", "external_reference": "r", "currency_id": "ARS"}, None, "ARS"),
    ({"id": 9, "status": "approved", "external_reference": "r", "transaction_amount": 10.5}, Decimal("10.5"), None),
    ({"id": 9, "status": "approved", "external_reference": "r", "transaction_amount": "abc", "currency_id": "ARS"}, None, "ARS"),
    ({"id": 9, "status": "approved", "external_reference": "r", "transaction_amount": None, "currency_id": 5}, None, None),
])
async def test_mercadopago_monto_o_moneda_ausente_o_ilegible_se_informa_como_none(cuerpo, monto, moneda) -> None:
    adaptador = _adaptador(httpx.MockTransport(lambda r: httpx.Response(200, json=cuerpo)))
    pago = await adaptador.obtener_pago("9")
    assert (pago.monto, pago.moneda) == (monto, moneda)
