"""Adaptador real de Mercado Pago (Checkout Pro) con ``httpx.AsyncClient`` (D1; R16, R17).

No usa el SDK oficial (es síncrono y bloquearía el event loop). El token nunca se loguea ni va
en mensajes de excepción. En tests se inyecta ``transport`` (``httpx.MockTransport``): sin red.
"""

import json
from datetime import datetime
from decimal import Decimal, InvalidOperation

import httpx

from app.pagos.pasarela import (
    PagoInexistenteError,
    PagoPasarela,
    PasarelaNoDisponibleError,
    PreferenciaCreada,
)
from app.shared.logger import get_logger

logger = get_logger(__name__)
TIMEOUT_SEGUNDOS = 10.0
_PLACEHOLDER_MONTO = "__MONTO_DECIMAL__"


class MercadoPagoPasarela:
    """Implementa ``PasarelaPagos`` contra la API de Mercado Pago."""

    def __init__(self, *, access_token: str, api_base_url: str, public_base_url: str,
                 api_public_base_url: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.__token = access_token
        self._api = api_base_url.rstrip("/")
        self._public = public_base_url.rstrip("/")
        self._api_public = api_public_base_url.rstrip("/")
        self._transport = transport

    def __repr__(self) -> str:
        return f"MercadoPagoPasarela(api={self._api!r})"

    def _cliente(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=TIMEOUT_SEGUNDOS, transport=self._transport)

    def _cabeceras(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.__token}", **(extra or {})}

    async def _enviar(self, metodo: str, ruta: str, *, cabeceras: dict[str, str] | None = None,
                      contenido: str | None = None) -> httpx.Response:
        try:
            async with self._cliente() as cliente:
                respuesta = await cliente.request(
                    metodo, f"{self._api}{ruta}", headers=self._cabeceras(cabeceras),
                    content=contenido.encode() if contenido is not None else None)
        except httpx.HTTPError as exc:
            logger.warning("mercadopago: error de red (%s)", type(exc).__name__)
            raise PasarelaNoDisponibleError("Mercado Pago no respondió") from None
        if respuesta.status_code == 404 and metodo == "GET":
            raise PagoInexistenteError(ruta)
        if respuesta.status_code >= 400:
            logger.warning("mercadopago: respuesta %s en %s", respuesta.status_code, metodo)
            raise PasarelaNoDisponibleError(f"Mercado Pago respondió {respuesta.status_code}")
        return respuesta

    async def crear_preferencia(self, *, turno_id: int, referencia_externa: str, monto: Decimal,
                                descripcion: str, vence_en: datetime) -> PreferenciaCreada:
        retorno = f"{self._public}/?pago=retorno&turno={turno_id}"
        cuerpo = {
            "items": [{"title": descripcion, "quantity": 1, "currency_id": "ARS",
                       "unit_price": _PLACEHOLDER_MONTO}],
            "external_reference": referencia_externa,
            "notification_url": f"{self._api_public}/api/webhooks/mercadopago",
            "back_urls": {"success": retorno, "pending": retorno, "failure": retorno},
            "auto_return": "approved",
            "expires": True,
            "expiration_date_to": vence_en.isoformat(timespec="milliseconds"),
        }
        # El monto viaja como literal numérico exacto (R4): nunca pasa por float.
        texto = json.dumps(cuerpo).replace(
            f'"{_PLACEHOLDER_MONTO}"', f"{monto.quantize(Decimal('0.01'))}")
        respuesta = await self._enviar(
            "POST", "/checkout/preferences", contenido=texto,
            cabeceras={"X-Idempotency-Key": referencia_externa, "Content-Type": "application/json"})
        datos = respuesta.json()
        return PreferenciaCreada(checkout_url=str(datos["init_point"]), preferencia_id=str(datos.get("id")))

    async def obtener_pago(self, payment_id: str) -> PagoPasarela:
        datos = (await self._enviar("GET", f"/v1/payments/{payment_id}")).json()
        # Un monto o una moneda ausentes o ilegibles se informan como None: el servicio falla cerrado (RN-SN-09).
        try:
            monto: Decimal | None = Decimal(str(datos["transaction_amount"]))
        except (KeyError, InvalidOperation):
            monto = None
        if monto is not None and not monto.is_finite():
            monto = None
        moneda = datos.get("currency_id")
        return PagoPasarela(
            id=str(datos["id"]), estado=str(datos["status"]),
            referencia_externa=datos.get("external_reference"),
            monto=monto, moneda=moneda if isinstance(moneda, str) and moneda else None)
