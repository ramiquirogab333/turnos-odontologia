"""Cálculo puro de importes de presupuesto (C-11, D6; O9, O11). Sin I/O. Todo en ``Decimal`` (R4).

bruto = precio × cantidad; cobertura = q(bruto × porcentaje / 100); diferencial = arancel_diferencial × cantidad;
a_cargo = bruto − cobertura + diferencial. Los totales suman las líneas ya redondeadas.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CERO = Decimal("0.00")
_CENTAVO = Decimal("0.01")
_CIEN = Decimal("100")


def _q(valor: Decimal) -> Decimal:
    """Redondeo half-up a centavos (no bancario)."""
    return valor.quantize(_CENTAVO, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class LineaCalculada:
    bruto: Decimal
    cobertura: Decimal
    diferencial: Decimal
    a_cargo: Decimal
    sin_cobertura: bool


@dataclass(frozen=True)
class Totales:
    subtotal: Decimal
    cobertura: Decimal
    diferencial: Decimal
    a_cargo: Decimal


def calcular_linea(precio_unitario: Decimal, cantidad: int, cobertura_porcentaje: Decimal | None,
                   arancel_diferencial: Decimal | None) -> LineaCalculada:
    """Importes de una línea. ``cobertura_porcentaje`` ``None`` = sin obra social o sin fila de nomenclador."""
    bruto = _q(precio_unitario * cantidad)
    if cobertura_porcentaje is None:
        return LineaCalculada(bruto, CERO, CERO, bruto, True)
    cobertura = _q(bruto * cobertura_porcentaje / _CIEN)
    diferencial = _q((arancel_diferencial or CERO) * cantidad)
    return LineaCalculada(bruto, cobertura, diferencial, bruto - cobertura + diferencial, False)


def totalizar(lineas: Sequence[LineaCalculada]) -> Totales:
    """Suma de las líneas ya redondeadas (nunca se redondea el total)."""
    subtotal = sum((l.bruto for l in lineas), CERO)
    cobertura = sum((l.cobertura for l in lineas), CERO)
    diferencial = sum((l.diferencial for l in lineas), CERO)
    return Totales(subtotal, cobertura, diferencial, subtotal - cobertura + diferencial)
