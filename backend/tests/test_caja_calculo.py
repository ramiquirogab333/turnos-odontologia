"""C-12 (2.1-2.2, 3.1): cálculo puro de la caja (sin base). Datos sintéticos (R19)."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.caja.calculo import (
    LineaCaja,
    Movimiento,
    agrupar,
    cerrable_desde,
    comparar,
    limites_del_dia,
)

BA = ZoneInfo("America/Argentina/Buenos_Aires")
T0 = datetime(2031, 11, 17, 12, 0, tzinfo=BA)


def mov(concepto: str, medio: str, importe: str) -> Movimiento:
    return Movimiento(concepto=concepto, medio=medio, importe=Decimal(importe), instante=T0)


def test_agrupar_devuelve_una_linea_por_concepto_y_medio_con_cantidad_y_totales() -> None:
    r = agrupar([mov("sena", "mercadopago", "3000.00"), mov("sena", "mercadopago", "2999.99"),
                 mov("pago_presupuesto", "transferencia", "1500.00")])
    assert [(x.concepto, x.medio, x.cantidad, x.total) for x in r.lineas] == [
        ("sena", "mercadopago", 2, Decimal("5999.99")),
        ("pago_presupuesto", "transferencia", 1, Decimal("1500.00"))]
    assert (r.total_ingresos, r.total_egresos, r.total_neto) == (
        Decimal("7499.99"), Decimal("0.00"), Decimal("7499.99"))


def test_agrupar_sin_movimientos_deja_los_tres_totales_en_cero_con_dos_decimales() -> None:
    r = agrupar([])
    assert r.lineas == []
    assert [str(x) for x in (r.total_ingresos, r.total_egresos, r.total_neto)] == ["0.00", "0.00", "0.00"]


def test_una_devolucion_resta_del_neto_y_suma_como_egreso() -> None:
    r = agrupar([mov("sena", "transferencia", "3000.00"), mov("devolucion_sena", "transferencia", "500.00")])
    assert (str(r.total_ingresos), str(r.total_egresos), str(r.total_neto)) == ("3000.00", "500.00", "2500.00")
    assert [x.concepto for x in r.lineas] == ["sena", "devolucion_sena"]


def test_agrupar_separa_los_medios_y_suma_centavos_sin_error_de_coma_flotante() -> None:
    r = agrupar([mov("sena", "mercadopago", "0.10"), mov("sena", "mercadopago", "0.20"),
                 mov("sena", "transferencia", "0.05")])
    por_medio = {x.medio: x for x in r.lineas}
    assert str(por_medio["mercadopago"].total) == "0.30" and por_medio["mercadopago"].cantidad == 2
    assert str(por_medio["transferencia"].total) == "0.05"
    assert str(r.total_neto) == "0.35"


def test_el_orden_de_las_lineas_no_depende_del_orden_de_entrada() -> None:
    a = agrupar([mov("devolucion_sena", "mercadopago", "1.00"), mov("sena", "transferencia", "2.00"),
                 mov("sena", "mercadopago", "3.00")])
    b = agrupar([mov("sena", "mercadopago", "3.00"), mov("sena", "transferencia", "2.00"),
                 mov("devolucion_sena", "mercadopago", "1.00")])
    assert a.lineas == b.lineas
    assert [(x.concepto, x.medio) for x in a.lineas] == [
        ("sena", "mercadopago"), ("sena", "transferencia"), ("devolucion_sena", "mercadopago")]


# --- 3.1 comparar y cerrable_desde ------------------------------------------------------------------------------

def linea(concepto: str, medio: str, cantidad: int, total: str) -> LineaCaja:
    return LineaCaja(concepto=concepto, medio=medio, cantidad=cantidad, total=Decimal(total))


def test_comparar_devuelve_lista_vacia_si_coinciden_sin_importar_el_orden() -> None:
    a = [linea("sena", "mercadopago", 1, "3000.00"), linea("pago_presupuesto", "transferencia", 1, "1500.00")]
    assert comparar(a, list(reversed(a))) == []


def test_comparar_informa_una_diferencia_por_linea_con_ambos_importes() -> None:
    cierre = [linea("sena", "mercadopago", 1, "3000.00"), linea("pago_presupuesto", "transferencia", 1, "1500.00")]
    actual = [linea("sena", "mercadopago", 1, "3000.00")]
    d = comparar(cierre, actual)
    assert len(d) == 1
    assert (d[0].concepto, d[0].medio, str(d[0].total_cierre), str(d[0].total_actual)) == (
        "pago_presupuesto", "transferencia", "1500.00", "0.00")
    assert (d[0].cantidad_cierre, d[0].cantidad_actual) == (1, 0)


def test_comparar_detecta_la_linea_que_solo_existe_ahora_y_el_cambio_de_cantidad_con_igual_total() -> None:
    d = comparar([linea("sena", "mercadopago", 1, "3000.00")],
                 [linea("sena", "mercadopago", 2, "3000.00"), linea("devolucion_sena", "transferencia", 1, "10.00")])
    assert {(x.concepto, x.medio) for x in d} == {("sena", "mercadopago"), ("devolucion_sena", "transferencia")}
    nueva = next(x for x in d if x.concepto == "devolucion_sena")
    assert (str(nueva.total_cierre), str(nueva.total_actual)) == ("0.00", "10.00")


def test_cerrable_desde_es_las_0015_del_dia_siguiente_con_el_offset_de_la_clinica() -> None:
    c = cerrable_desde(date(2031, 11, 17), BA)
    assert c == datetime(2031, 11, 18, 0, 15, tzinfo=BA)
    assert c.utcoffset() == timedelta(hours=-3)
    assert c.astimezone(timezone.utc) == datetime(2031, 11, 18, 3, 15, tzinfo=timezone.utc)
    assert cerrable_desde(date(2031, 12, 31), BA) == datetime(2032, 1, 1, 0, 15, tzinfo=BA)  # cambio de año


def test_limites_del_dia_son_medianoche_a_medianoche_de_la_clinica_en_utc() -> None:
    desde, hasta = limites_del_dia(date(2031, 11, 17), BA)
    assert desde == datetime(2031, 11, 17, 3, 0, tzinfo=timezone.utc)
    assert hasta == datetime(2031, 11, 18, 3, 0, tzinfo=timezone.utc)
    assert desde.utcoffset() == timedelta(0)
