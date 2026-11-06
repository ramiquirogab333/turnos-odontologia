"""Cálculo puro de la seña: monto (RN-SN-03) y vencimiento (RN-SN-07). Sin I/O (R4, R13)."""

from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

_CENTAVOS = Decimal("0.01")
_CIEN = Decimal(100)


def monto_sena(precio_base: Decimal, porcentaje: Decimal) -> Decimal:
    """Seña = precio_base * porcentaje / 100, a 2 decimales con redondeo half-up (nunca float)."""
    return (precio_base * porcentaje / _CIEN).quantize(_CENTAVOS, rounding=ROUND_HALF_UP)


def vencimiento(ahora: datetime, minutos: int, inicio: datetime) -> datetime:
    """Instante en que vence una pre-reserva: ``ahora + minutos``, sin pasar del inicio del turno."""
    return min(ahora + timedelta(minutes=minutos), inicio)
