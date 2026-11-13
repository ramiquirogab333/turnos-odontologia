"""C-13 (7.1, D9, O11-O13): núcleo puro de la exportación — neutralización, formato, dialecto y descriptores. Sintético."""

import csv
import io
from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.plataforma.exportacion import (
    BOM,
    DESCRIPTORES,
    EscritorCsv,
    formatear_valor,
    neutralizar_celda,
)

BA = ZoneInfo("America/Argentina/Buenos_Aires")


# --- Neutralización de fórmulas (O13) ------------------------------------------------------------------------------

@pytest.mark.parametrize("inicio", ["=", "+", "-", "@", "\t", "\r"])
def test_un_texto_libre_que_empieza_con_un_prefijo_peligroso_lleva_apostrofo(inicio: str) -> None:
    valor = f'{inicio}HYPERLINK("http://example.invalid","ver")'
    assert neutralizar_celda(valor) == "'" + valor


@pytest.mark.parametrize("valor", ["Lucía Ejemplo", "Mateo-Prueba", "a=b", "x+y", "", "  =no al inicio", "'ya con apóstrofo"])
def test_un_texto_normal_o_con_el_prefijo_en_el_medio_no_se_toca(valor: str) -> None:
    assert neutralizar_celda(valor) == valor


# --- Formato de valores (O12) ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("valor,tipo,esperado", [
    (None, "texto_libre", ""), (None, "decimal", ""), (None, "instante", ""),
    (Decimal("15000"), "decimal", "15000.00"), (Decimal("0"), "decimal", "0.00"), (Decimal("1234.5"), "decimal", "1234.50"),
    (datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc), "instante", "2026-11-16T09:00:00-03:00"),
    (datetime(2026, 11, 16, 3, 30, tzinfo=timezone.utc), "instante", "2026-11-16T00:30:00-03:00"),
    (date(2026, 11, 4), "fecha", "2026-11-04"),
    (True, "booleano", "true"), (False, "booleano", "false"),
    (501, "entero", "501"),
    ("+5491100000001", "telefono", "+5491100000001"),  # E.164 validado: sin apóstrofo
    ("=cmd", "texto_libre", "'=cmd"),
    ("vigente", "codigo", "vigente"),
])
def test_formatear_valor(valor: object, tipo: str, esperado: str) -> None:
    assert formatear_valor(valor, tipo, BA) == esperado


def test_los_decimales_nunca_pasan_por_float() -> None:
    assert formatear_valor(Decimal("0.10") + Decimal("0.20"), "decimal", BA) == "0.30"
    assert formatear_valor(Decimal("99999999999.99"), "decimal", BA) == "99999999999.99"


# --- Dialecto: RFC 4180, BOM solo al principio, CRLF ------------------------------------------------------------------

def _leer(texto: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(texto.removeprefix(BOM), newline="")))


def test_el_bom_va_solo_en_el_primer_trozo_y_las_lineas_terminan_en_crlf() -> None:
    escritor = EscritorCsv(("a", "b"))
    cabecera = escritor.encabezado()
    lote = escritor.filas([["1", "x"], ["2", "y"]])
    assert cabecera.startswith(BOM) and BOM not in lote and BOM not in cabecera[1:]
    assert cabecera == BOM + "a,b\r\n" and lote == "1,x\r\n2,y\r\n"
    assert "\n" not in (cabecera + lote).replace("\r\n", "")


def test_comas_comillas_y_saltos_de_linea_se_escapan_y_la_fila_conserva_sus_columnas() -> None:
    escritor = EscritorCsv(("id", "motivo", "otro"))
    texto = escritor.encabezado() + escritor.filas([["1", 'Error de carga, "duplicado"', "ok"],
                                                    ["2", "línea 1\nlínea 2", "ñandú"]])
    assert '"Error de carga, ""duplicado"""' in texto
    filas = _leer(texto)
    assert filas[1] == ["1", 'Error de carga, "duplicado"', "ok"] and filas[2] == ["2", "línea 1\nlínea 2", "ñandú"]
    assert all(len(f) == 3 for f in filas)


def test_un_lote_vacio_no_emite_nada() -> None:
    assert EscritorCsv(("a",)).filas([]) == ""


# --- Descriptores por entidad (O11) -------------------------------------------------------------------------------------

def test_los_descriptores_de_turnos_pacientes_y_cierres_tienen_las_columnas_exactas_y_en_orden() -> None:
    nombres = {e: tuple(c.nombre for c in d.columnas) for e, d in DESCRIPTORES.items()}
    assert nombres["turnos"] == ("id", "inicio", "fin", "estado", "origen", "profesional_id", "profesional", "sillon_id",
                                 "sillon", "tratamiento_id", "tratamiento", "paciente_id", "contacto_nombre",
                                 "contacto_telefono")
    assert nombres["pacientes"] == ("id", "nombre", "apellido", "dni", "telefono", "email", "obra_social",
                                    "numero_afiliado", "activo", "creado_en")
    assert nombres["cierres_caja"] == ("id", "dia", "estado", "total_ingresos", "total_egresos", "total_neto",
                                       "cerrado_por", "cerrado_en", "anulado_por", "anulado_en", "anulado_motivo",
                                       "observaciones")
    assert set(DESCRIPTORES) == {"turnos", "pacientes", "cierres_caja"}


@pytest.mark.parametrize("prohibida", ["codigo_gestion", "periodo", "mp_payment_id", "referencia_externa", "alergias",
                                       "medicacion", "antecedentes_medicos", "google_event_id", "token"])
def test_ninguna_exportacion_incluye_codigos_de_gestion_pasarela_ni_datos_clinicos(prohibida: str) -> None:
    assert all(prohibida not in {c.nombre for c in d.columnas} for d in DESCRIPTORES.values())


def test_los_telefonos_e164_no_son_texto_libre_y_los_nombres_si() -> None:
    tipos = {(e, c.nombre): c.tipo for e, d in DESCRIPTORES.items() for c in d.columnas}
    assert tipos[("turnos", "contacto_telefono")] == tipos[("pacientes", "telefono")] == "telefono"
    for clave in [("turnos", "contacto_nombre"), ("turnos", "profesional"), ("pacientes", "nombre"),
                  ("pacientes", "email"), ("pacientes", "numero_afiliado"), ("cierres_caja", "anulado_motivo"),
                  ("cierres_caja", "observaciones"), ("cierres_caja", "cerrado_por")]:
        assert tipos[clave] == "texto_libre", clave
    assert tipos[("turnos", "id")] == "entero" and tipos[("cierres_caja", "total_neto")] == "decimal"
    assert tipos[("turnos", "inicio")] == "instante" and tipos[("cierres_caja", "dia")] == "fecha"
    assert tipos[("pacientes", "activo")] == "booleano"


def test_el_dni_y_los_codigos_de_estado_no_se_neutralizan() -> None:
    tipos = {(e, c.nombre): c.tipo for e, d in DESCRIPTORES.items() for c in d.columnas}
    assert tipos[("pacientes", "dni")] == "codigo" and tipos[("turnos", "estado")] == "codigo"
    assert tipos[("turnos", "origen")] == "codigo" and tipos[("cierres_caja", "estado")] == "codigo"
