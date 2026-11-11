"""Cálculo puro de la caja (C-12, D2/D3): agrupar movimientos y comparar un cierre con la caja actual. Sin I/O.

Todo importe es ``Decimal`` con dos cifras (R4); nunca ``float``.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from decimal import Decimal
from typing import Final

CENTAVO: Final[Decimal] = Decimal("0.01")
MARGEN_CIERRE: Final[timedelta] = timedelta(minutes=15)

CONCEPTOS_INGRESO: Final[tuple[str, ...]] = ("sena", "pago_presupuesto")
CONCEPTOS_EGRESO: Final[tuple[str, ...]] = ("devolucion_sena",)
ORDEN_CONCEPTOS: Final[tuple[str, ...]] = CONCEPTOS_INGRESO + CONCEPTOS_EGRESO
ORDEN_MEDIOS: Final[tuple[str, ...]] = ("mercadopago", "transferencia")


def dos_decimales(valor: Decimal) -> Decimal:
    return valor.quantize(CENTAVO)


@dataclass(frozen=True)
class Movimiento:
    """Un movimiento de caja: concepto, medio, importe recibido o devuelto e instante en que ocurrió."""

    concepto: str
    medio: str
    importe: Decimal
    instante: datetime
    referencia: str | None = None
    turno_id: int | None = None
    presupuesto_id: int | None = None
    pago_id: int | None = None


@dataclass(frozen=True)
class LineaCaja:
    concepto: str
    medio: str
    cantidad: int
    total: Decimal


@dataclass(frozen=True)
class ResumenCaja:
    lineas: list[LineaCaja]
    total_ingresos: Decimal
    total_egresos: Decimal
    total_neto: Decimal


@dataclass(frozen=True)
class Diferencia:
    concepto: str
    medio: str
    total_cierre: Decimal
    total_actual: Decimal
    cantidad_cierre: int
    cantidad_actual: int


def _clave_orden(concepto: str, medio: str) -> tuple[int, int]:
    return ORDEN_CONCEPTOS.index(concepto), ORDEN_MEDIOS.index(medio)


def armar_resumen(lineas: Iterable[LineaCaja]) -> ResumenCaja:
    """Ordena las líneas y calcula los tres totales a partir de ellas."""
    ordenadas = sorted(lineas, key=lambda x: _clave_orden(x.concepto, x.medio))
    ingresos = sum((x.total for x in ordenadas if x.concepto in CONCEPTOS_INGRESO), Decimal("0.00"))
    egresos = sum((x.total for x in ordenadas if x.concepto in CONCEPTOS_EGRESO), Decimal("0.00"))
    ingresos, egresos = dos_decimales(ingresos), dos_decimales(egresos)
    return ResumenCaja(lineas=ordenadas, total_ingresos=ingresos, total_egresos=egresos,
                       total_neto=dos_decimales(ingresos - egresos))


def agrupar(movimientos: Iterable[Movimiento]) -> ResumenCaja:
    """Una línea por concepto y medio con cantidad y total, y los totales de ingresos, egresos y neto."""
    acumulado: dict[tuple[str, str], tuple[int, Decimal]] = {}
    for m in movimientos:
        cantidad, total = acumulado.get((m.concepto, m.medio), (0, Decimal("0.00")))
        acumulado[(m.concepto, m.medio)] = (cantidad + 1, total + m.importe)
    return armar_resumen(LineaCaja(c, med, n, dos_decimales(t)) for (c, med), (n, t) in acumulado.items())


def comparar(lineas_cierre: Iterable[LineaCaja], lineas_actuales: Iterable[LineaCaja]) -> list[Diferencia]:
    """Diferencias por concepto y medio entre un cierre y los movimientos recalculados (lista vacía si coinciden)."""
    cero = Decimal("0.00")
    del_cierre = {(x.concepto, x.medio): x for x in lineas_cierre}
    actuales = {(x.concepto, x.medio): x for x in lineas_actuales}
    diferencias: list[Diferencia] = []
    for clave in sorted(del_cierre.keys() | actuales.keys(), key=lambda k: _clave_orden(*k)):
        a, b = del_cierre.get(clave), actuales.get(clave)
        total_a, total_b = (a.total if a else cero), (b.total if b else cero)
        cant_a, cant_b = (a.cantidad if a else 0), (b.cantidad if b else 0)
        if total_a != total_b or cant_a != cant_b:
            diferencias.append(Diferencia(clave[0], clave[1], dos_decimales(total_a), dos_decimales(total_b),
                                          cant_a, cant_b))
    return diferencias


def cerrable_desde(dia: date, zona: tzinfo) -> datetime:
    """Primer instante en que se puede cerrar ``dia``: las 00:15 del día siguiente en la hora de la clínica (O1)."""
    return datetime.combine(dia + timedelta(days=1), time.min, tzinfo=zona) + MARGEN_CIERRE


def limites_del_dia(dia: date, zona: tzinfo) -> tuple[datetime, datetime]:
    """``[00:00, 24:00)`` del día de la clínica convertido a UTC (mismo criterio que ``rango_utc`` de C-08)."""
    desde = datetime.combine(dia, time.min, tzinfo=zona).astimezone(timezone.utc)
    hasta = datetime.combine(dia + timedelta(days=1), time.min, tzinfo=zona).astimezone(timezone.utc)
    return desde, hasta
