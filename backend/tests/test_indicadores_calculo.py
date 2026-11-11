"""C-12 (6.1): cálculo puro de los indicadores (sin base). Datos sintéticos (R19)."""

from datetime import time
from decimal import Decimal

from app.panel.calculo_indicadores import minutos_de_atencion, porcentaje, tasa


def t(h: int, m: int = 0) -> time:
    return time(h, m)


def test_franjas_separadas_suman_sus_duraciones() -> None:
    assert minutos_de_atencion([(t(9), t(13)), (t(15), t(18))]) == 240 + 180


def test_franjas_superpuestas_no_se_cuentan_dos_veces() -> None:
    assert minutos_de_atencion([(t(9), t(13)), (t(11), t(15))]) == 360


def test_franjas_contenidas_o_contiguas_y_en_cualquier_orden() -> None:
    assert minutos_de_atencion([(t(11), t(12)), (t(9), t(13))]) == 240  # una dentro de la otra
    assert minutos_de_atencion([(t(13), t(14)), (t(9), t(13))]) == 300  # contiguas: sin hueco ni solape
    assert minutos_de_atencion([(t(9, 15), t(9, 45)), (t(9, 30), t(10, 10))]) == 55


def test_sin_franjas_son_cero_minutos() -> None:
    assert minutos_de_atencion([]) == 0


def test_porcentaje_con_dos_decimales_y_vacio_si_no_hay_atencion() -> None:
    assert porcentaje(90, 240) == Decimal("37.50")
    assert porcentaje(0, 240) == Decimal("0.00")
    assert porcentaje(30, 0) is None
    assert porcentaje(0, 0) is None


def test_porcentaje_redondea_half_up_en_el_centavo_y_puede_superar_100() -> None:
    assert porcentaje(1, 800) == Decimal("0.13")  # 0.125 -> 0.13 (half-up; con redondeo bancario daría 0.12)
    assert porcentaje(1, 3) == Decimal("33.33")
    assert porcentaje(2, 3) == Decimal("66.67")
    assert porcentaje(300, 240) == Decimal("125.00")  # la disponibilidad actual puede ser menor que la histórica
    assert str(porcentaje(240, 240)) == "100.00"


def test_tasa_de_ausentismo_es_ausentes_sobre_atendidos_mas_ausentes() -> None:
    assert tasa(2, 8) == Decimal("20.00")
    assert tasa(1, 2) == Decimal("33.33")
    assert tasa(0, 5) == Decimal("0.00")
    assert tasa(3, 0) == Decimal("100.00")


def test_tasa_sin_turnos_resueltos_es_vacia() -> None:
    assert tasa(0, 0) is None
