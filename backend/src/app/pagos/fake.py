"""Pasarela falsa determinística y sin estado (D1). SOLO para tests, CI y E2E; prohibida en producción.

Backend (Docker) y runner de Playwright no comparten memoria, así que el estado del pago viaja
en el propio id: ``fake-<estado>-<referencia_externa>[@<monto>[@<moneda>]]``.
El monto y la moneda opcionales permiten probar discrepancias (RN-SN-09) sin red.
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.pagos.pasarela import PagoInexistenteError, PagoPasarela, PreferenciaCreada

_PREFIJO = "fake-"


class FakePasarela:
    """Implementa ``PasarelaPagos`` sin red ni estado compartido."""

    def __init__(self, public_base_url: str) -> None:
        self._public_base_url = public_base_url.rstrip("/")

    async def crear_preferencia(self, *, turno_id: int, referencia_externa: str, monto: Decimal,
                                descripcion: str, vence_en: datetime) -> PreferenciaCreada:
        return PreferenciaCreada(checkout_url=f"{self._public_base_url}/?pago=retorno&turno={turno_id}")

    async def obtener_pago(self, payment_id: str) -> PagoPasarela:
        if not payment_id.startswith(_PREFIJO):
            raise PagoInexistenteError(payment_id)
        cuerpo, *extras = payment_id[len(_PREFIJO):].split("@")
        estado, _, referencia = cuerpo.partition("-")
        if not estado or not referencia or len(extras) > 2:
            raise PagoInexistenteError(payment_id)
        try:
            monto = Decimal(extras[0]) if extras else None
        except InvalidOperation:
            raise PagoInexistenteError(payment_id) from None
        moneda = extras[1] if len(extras) == 2 else None
        return PagoPasarela(id=payment_id, estado=estado, referencia_externa=referencia, monto=monto, moneda=moneda)
