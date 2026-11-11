"""Cálculo puro de los indicadores del panel (C-12, D7): minutos de atención, porcentaje y tasa. Sin I/O.

Importes y porcentajes son ``Decimal`` con redondeo half-up a dos cifras (R4); nunca ``float``.
"""

from collections.abc import Iterable
from datetime import time
from decimal import ROUND_HALF_UP, Decimal
from typing import Final

CENTAVO: Final[Decimal] = Decimal("0.01")
CIEN: Final[Decimal] = Decimal(100)


def _minutos(valor: time) -> int:
    return valor.hour * 60 + valor.minute


def minutos_de_atencion(franjas: Iterable[tuple[time, time]]) -> int:
    """Duración de la UNIÓN de las franjas: las que se superponen o se tocan no se cuentan dos veces."""
    intervalos = sorted((_minutos(a), _minutos(b)) for a, b in franjas)
    total, actual_fin = 0, -1
    for inicio, fin in intervalos:
        if fin <= inicio:
            continue
        if inicio > actual_fin:
            total += fin - inicio
            actual_fin = fin
        elif fin > actual_fin:
            total += fin - actual_fin
            actual_fin = fin
    return total


def _porcentaje(parte: int, total: int) -> Decimal:
    return (Decimal(parte) * CIEN / Decimal(total)).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def porcentaje(ocupados: int, atencion: int) -> Decimal | None:
    """Ocupación en porcentaje con dos decimales; ``None`` si no hay minutos de atención (sin dividir por cero)."""
    if atencion <= 0:
        return None
    return _porcentaje(ocupados, atencion)


def tasa(ausentes: int, atendidos: int) -> Decimal | None:
    """Ausentismo = ausentes / (atendidos + ausentes) en porcentaje; ``None`` si no hay turnos resueltos (O12)."""
    resueltos = ausentes + atendidos
    if resueltos <= 0:
        return None
    return _porcentaje(ausentes, resueltos)
