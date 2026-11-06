"""C-06 (2.1): cálculo puro de monto de seña (RN-SN-03) y vencimiento (RN-SN-07). Sin DB."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.pagos.calculo import monto_sena, vencimiento

INICIO = datetime(2031, 3, 3, 13, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("precio,porcentaje,esperado", [
    ("10000.00", "30", "3000.00"),
    ("3333.33", "30", "1000.00"),   # 999.999 -> half-up
    ("0.05", "30", "0.02"),         # 0.015 -> 0.02 (half-up, no bancario)
    ("15000.00", "100", "15000.00"),
    ("0", "30", "0.00"),            # precio 0: exento (RN-SN-06)
])
def test_monto_sena_half_up_con_dos_decimales(precio: str, porcentaje: str, esperado: str) -> None:
    monto = monto_sena(Decimal(precio), Decimal(porcentaje))
    assert monto == Decimal(esperado)
    assert isinstance(monto, Decimal) and monto.as_tuple().exponent == -2


def test_vencimiento_suma_minutos() -> None:
    ahora = INICIO - timedelta(days=2)
    assert vencimiento(ahora, 30, INICIO) == ahora + timedelta(minutes=30)
    assert vencimiento(ahora, 1440, INICIO) == ahora + timedelta(hours=24)


def test_vencimiento_no_pasa_del_inicio_del_turno() -> None:
    ahora = INICIO - timedelta(minutes=10)
    assert vencimiento(ahora, 30, INICIO) == INICIO
    assert vencimiento(INICIO - timedelta(hours=30), 1440, INICIO) == INICIO - timedelta(hours=6)
