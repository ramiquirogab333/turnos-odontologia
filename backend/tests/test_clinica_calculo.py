"""C-11 (2.1): cálculo puro de importes de presupuesto, sin base. Datos sintéticos (R19)."""

from decimal import Decimal

from app.clinica.calculo import LineaCalculada, calcular_linea, totalizar

D = Decimal


def test_limpieza_al_90_por_ciento() -> None:
    r = calcular_linea(D("25000.00"), 1, D("90.00"), D("0.00"))
    assert (r.bruto, r.cobertura, r.diferencial, r.a_cargo) == (D("25000.00"), D("22500.00"), D("0.00"), D("2500.00"))
    assert r.sin_cobertura is False


def test_redondeo_half_up_no_bancario() -> None:
    """10.10 × 85 % = 8.585: half-up da 8.59 (el redondeo bancario daría 8.58)."""
    r = calcular_linea(D("10.10"), 1, D("85.00"), D("0.00"))
    assert r.cobertura == D("8.59")
    assert r.a_cargo == D("1.51")


def test_diferencial_se_multiplica_por_la_cantidad() -> None:
    r = calcular_linea(D("25000.00"), 2, D("90.00"), D("1500.00"))
    assert (r.bruto, r.cobertura, r.diferencial, r.a_cargo) == (
        D("50000.00"), D("45000.00"), D("3000.00"), D("8000.00"))


def test_sin_cobertura_cuando_no_hay_fila_de_nomenclador() -> None:
    r = calcular_linea(D("25000.00"), 1, None, None)
    assert (r.cobertura, r.diferencial, r.a_cargo) == (D("0.00"), D("0.00"), D("25000.00"))
    assert r.sin_cobertura is True


def test_cobertura_total_sin_diferencial_deja_cero_a_cargo() -> None:
    r = calcular_linea(D("15000.00"), 3, D("100.00"), D("0.00"))
    assert r.a_cargo == D("0.00")
    assert r.sin_cobertura is False


def test_totales_son_la_suma_de_las_lineas_ya_redondeadas() -> None:
    """Dos líneas de 10.10 al 85 %: 8.59 + 8.59 = 17.18, no 17.17 (redondear el total daría otro centavo)."""
    linea = calcular_linea(D("10.10"), 1, D("85.00"), D("0.00"))
    t = totalizar([linea, linea])
    assert t.subtotal == D("20.20")
    assert t.cobertura == D("17.18")
    assert t.a_cargo == D("3.02")
    assert t.a_cargo == t.subtotal - t.cobertura + t.diferencial


def test_totales_de_dos_lineas_swiss() -> None:
    limpieza = calcular_linea(D("25000.00"), 1, D("90.00"), D("0.00"))
    consulta = calcular_linea(D("15000.00"), 1, D("90.00"), D("0.00"))
    t = totalizar([limpieza, consulta])
    assert (t.subtotal, t.cobertura, t.diferencial, t.a_cargo) == (
        D("40000.00"), D("36000.00"), D("0.00"), D("4000.00"))


def test_totalizar_lista_vacia_es_cero() -> None:
    t = totalizar([])
    assert (t.subtotal, t.cobertura, t.diferencial, t.a_cargo) == (D("0.00"),) * 4


def test_linea_calculada_es_inmutable() -> None:
    r: LineaCalculada = calcular_linea(D("1.00"), 1, None, None)
    try:
        r.bruto = D("2.00")  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("LineaCalculada debería ser frozen")
