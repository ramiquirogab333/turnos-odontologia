"""Exportación de datos en CSV (C-13, D9; O11-O13): descriptores de columnas, formato, dialecto y consultas.

Núcleo sin I/O: ``neutralizar_celda`` y ``formatear_valor`` son funciones puras, ``EscritorCsv`` arma texto por lotes
(RFC 4180, comas, CRLF, BOM solo en el primer trozo) y ``consulta`` devuelve el ``SELECT`` de cada entidad con sus joins
(sin N+1) en el orden exacto de las columnas. Nunca salen ``codigo_gestion``, ids de pasarela, datos de Google ni datos
clínicos. Los decimales no pasan por ``float`` (R4).
"""

import csv
import io
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Final, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import Select, select
from sqlalchemy.orm import aliased

from app.caja.models import CierreCaja
from app.models.core import ObraSocial, Paciente, Usuario
from app.turnos.models import Profesional, Sillon, Tratamiento, Turno

BOM: Final = "﻿"
PREFIJOS_DE_FORMULA: Final = ("=", "+", "-", "@", "\t", "\r")
Tipo = Literal["entero", "codigo", "texto_libre", "telefono", "decimal", "instante", "fecha", "booleano"]
Entidad = Literal["turnos", "pacientes", "cierres_caja"]
CENTAVOS: Final = Decimal("0.01")


@dataclass(frozen=True)
class Columna:
    nombre: str
    tipo: Tipo


@dataclass(frozen=True)
class Descriptor:
    entidad: str
    columnas: tuple[Columna, ...]


def _c(nombre: str, tipo: Tipo) -> Columna:
    return Columna(nombre, tipo)


DESCRIPTORES: Final[dict[str, Descriptor]] = {
    "turnos": Descriptor("turnos", (
        _c("id", "entero"), _c("inicio", "instante"), _c("fin", "instante"), _c("estado", "codigo"),
        _c("origen", "codigo"), _c("profesional_id", "entero"), _c("profesional", "texto_libre"),
        _c("sillon_id", "entero"), _c("sillon", "texto_libre"), _c("tratamiento_id", "entero"),
        _c("tratamiento", "texto_libre"), _c("paciente_id", "entero"), _c("contacto_nombre", "texto_libre"),
        _c("contacto_telefono", "telefono"))),
    "pacientes": Descriptor("pacientes", (
        _c("id", "entero"), _c("nombre", "texto_libre"), _c("apellido", "texto_libre"), _c("dni", "codigo"),
        _c("telefono", "telefono"), _c("email", "texto_libre"), _c("obra_social", "texto_libre"),
        _c("numero_afiliado", "texto_libre"), _c("activo", "booleano"), _c("creado_en", "instante"))),
    "cierres_caja": Descriptor("cierres_caja", (
        _c("id", "entero"), _c("dia", "fecha"), _c("estado", "codigo"), _c("total_ingresos", "decimal"),
        _c("total_egresos", "decimal"), _c("total_neto", "decimal"), _c("cerrado_por", "texto_libre"),
        _c("cerrado_en", "instante"), _c("anulado_por", "texto_libre"), _c("anulado_en", "instante"),
        _c("anulado_motivo", "texto_libre"), _c("observaciones", "texto_libre"))),
}


def neutralizar_celda(valor: str) -> str:
    """Antepone un apóstrofo si la celda empieza con un prefijo que una planilla ejecutaría como fórmula (OWASP)."""
    return "'" + valor if valor.startswith(PREFIJOS_DE_FORMULA) else valor


def formatear_valor(valor: object, tipo: Tipo, zona: ZoneInfo) -> str:
    """Texto de una celda: nulos vacíos, decimales con dos posiciones, instantes ISO-8601 en la zona de la clínica."""
    if valor is None:
        return ""
    if tipo == "decimal":
        return format(Decimal(str(valor)).quantize(CENTAVOS), "f")
    if tipo == "instante":
        assert isinstance(valor, datetime)
        return valor.astimezone(zona).isoformat(timespec="seconds")
    if tipo == "fecha":
        assert isinstance(valor, date)
        return valor.isoformat()
    if tipo == "booleano":
        return "true" if valor else "false"
    texto = str(valor)
    return neutralizar_celda(texto) if tipo == "texto_libre" else texto


def formatear_fila(valores: Sequence[object], columnas: Sequence[Columna], zona: ZoneInfo) -> list[str]:
    return [formatear_valor(v, c.tipo, zona) for v, c in zip(valores, columnas, strict=True)]


class EscritorCsv:
    """Arma el CSV por trozos de texto: el BOM sale solo con el encabezado; cada lote termina en CRLF."""

    def __init__(self, encabezado: Sequence[str]) -> None:
        self._encabezado = list(encabezado)

    @staticmethod
    def _serializar(filas: Sequence[Sequence[str]]) -> str:
        buffer = io.StringIO(newline="")
        csv.writer(buffer, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n").writerows(filas)
        return buffer.getvalue()

    def encabezado(self) -> str:
        return BOM + self._serializar([self._encabezado])

    def filas(self, filas: Sequence[Sequence[str]]) -> str:
        return self._serializar(filas) if filas else ""


# --- Consultas (una por entidad, con sus joins; el orden de columnas coincide con el descriptor) -------------------------

@dataclass(frozen=True)
class Filtros:
    desde: date | None = None
    hasta: date | None = None
    incluir_inactivos: bool = False


def _limites(filtros: Filtros, zona: ZoneInfo) -> tuple[datetime | None, datetime | None]:
    """Instantes ``[inicio, fin)`` de los días locales ``desde``/``hasta`` (el de ``hasta`` entero)."""
    inicio = None if filtros.desde is None else datetime.combine(filtros.desde, time.min, tzinfo=zona)
    fin = None if filtros.hasta is None else datetime.combine(filtros.hasta + timedelta(days=1), time.min, tzinfo=zona)
    return inicio, fin


def consulta(entidad: str, filtros: Filtros, zona: ZoneInfo) -> Select[tuple[object, ...]]:
    """``SELECT`` de la entidad con los filtros; ``KeyError`` si la entidad no se exporta."""
    if entidad == "turnos":
        sql = (select(Turno.id, Turno.inicio, Turno.fin, Turno.estado, Turno.origen, Turno.profesional_id,
                      Profesional.nombre, Turno.sillon_id, Sillon.nombre, Turno.tratamiento_id, Tratamiento.nombre,
                      Turno.paciente_id, Turno.contacto_nombre, Turno.contacto_telefono)
               .join(Profesional, Profesional.id == Turno.profesional_id)
               .join(Sillon, Sillon.id == Turno.sillon_id)
               .join(Tratamiento, Tratamiento.id == Turno.tratamiento_id)
               .order_by(Turno.inicio, Turno.id))
        inicio, fin = _limites(filtros, zona)
        if inicio is not None:
            sql = sql.where(Turno.inicio >= inicio)
        if fin is not None:
            sql = sql.where(Turno.inicio < fin)
        return sql
    if entidad == "pacientes":
        sql = (select(Paciente.id, Paciente.nombre, Paciente.apellido, Paciente.dni, Paciente.telefono, Paciente.email,
                      ObraSocial.nombre, Paciente.numero_afiliado, Paciente.is_active, Paciente.created_at)
               .outerjoin(ObraSocial, ObraSocial.id == Paciente.obra_social_id).order_by(Paciente.id))
        return sql if filtros.incluir_inactivos else sql.where(Paciente.is_active.is_(True))
    if entidad == "cierres_caja":
        cerro, anulo = aliased(Usuario), aliased(Usuario)
        sql = (select(CierreCaja.id, CierreCaja.dia, CierreCaja.estado, CierreCaja.total_ingresos,
                      CierreCaja.total_egresos, CierreCaja.total_neto, cerro.nombre_completo, CierreCaja.cerrado_en,
                      anulo.nombre_completo, CierreCaja.anulado_en, CierreCaja.anulado_motivo, CierreCaja.observaciones)
               .outerjoin(cerro, cerro.id == CierreCaja.cerrado_por)
               .outerjoin(anulo, anulo.id == CierreCaja.anulado_por).order_by(CierreCaja.dia, CierreCaja.id))
        if filtros.desde is not None:
            sql = sql.where(CierreCaja.dia >= filtros.desde)
        if filtros.hasta is not None:
            sql = sql.where(CierreCaja.dia <= filtros.hasta)
        return sql
    raise KeyError(entidad)
