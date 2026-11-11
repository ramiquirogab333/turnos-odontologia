"""Esquemas Pydantic de la caja (C-12, R15): ``extra="forbid"`` en toda entrada y salida.

Los importes viajan como texto decimal de dos cifras (R4). Ninguna salida lleva nombre, DNI, teléfono ni email (R19).
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, PlainSerializer, StringConstraints, field_validator, model_validator

Dinero = Annotated[Decimal, PlainSerializer(lambda v: f"{v:.2f}", return_type=str, when_used="json")]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LineaCajaOut(_Base):
    concepto: Literal["sena", "pago_presupuesto", "devolucion_sena"]
    medio: Literal["mercadopago", "transferencia"]
    cantidad: int
    total: Dinero


class SenasRetenidasOut(_Base):
    """Señas del día cuyo turno quedó ``ausente`` (``no_reembolsado``, R9): siguen siendo ingreso."""

    cantidad: int
    total: Dinero


class MovimientoOut(_Base):
    concepto: Literal["sena", "pago_presupuesto", "devolucion_sena"]
    medio: Literal["mercadopago", "transferencia"]
    importe: Dinero
    hora: datetime
    referencia: str | None
    turno_id: int | None
    presupuesto_id: int | None


class CajaOut(_Base):
    dia: date
    estado: Literal["abierto", "cerrado"]
    cierre_id: int | None
    lineas: list[LineaCajaOut]
    total_ingresos: Dinero
    total_egresos: Dinero
    total_neto: Dinero
    senas_retenidas: SenasRetenidasOut
    movimientos: list[MovimientoOut]


# --- Cierre de caja y liquidación (grupo 3) -----------------------------------------------------------------

Motivo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=300)]
Observaciones = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
MAX_DIAS_RANGO = 366


class CierreCreateIn(_Base):
    """El cliente solo elige el día: los importes los calcula el servidor (``extra="forbid"``)."""

    dia: date
    observaciones: Observaciones | None = None


class AnularCierreIn(_Base):
    motivo: Motivo


class RangoFechas(_Base):
    """``desde`` y ``hasta`` inclusivos, hasta 366 días."""

    desde: date
    hasta: date

    @model_validator(mode="after")
    def _rango(self) -> "RangoFechas":
        if self.hasta < self.desde:
            raise ValueError("hasta no puede ser anterior a desde")
        if (self.hasta - self.desde).days >= MAX_DIAS_RANGO:
            raise ValueError(f"el rango no puede superar {MAX_DIAS_RANGO} días")
        return self


class CierreResumenOut(_Base):
    id: int
    dia: date
    estado: Literal["vigente", "anulado"]
    total_ingresos: Dinero
    total_egresos: Dinero
    total_neto: Dinero
    observaciones: str | None
    cerrado_por: int | None
    cerrado_por_nombre: str | None
    cerrado_en: datetime
    anulado_por: int | None
    anulado_en: datetime | None
    anulado_motivo: str | None


class CierreOut(CierreResumenOut):
    lineas: list[LineaCajaOut]


class DiferenciaOut(_Base):
    concepto: Literal["sena", "pago_presupuesto", "devolucion_sena"]
    medio: Literal["mercadopago", "transferencia"]
    total_cierre: Dinero
    total_actual: Dinero
    cantidad_cierre: int
    cantidad_actual: int


class CierreDetalleOut(CierreOut):
    """``cuadra`` es ``None`` en un cierre anulado (ya no vale como foto)."""

    cuadra: bool | None
    diferencias: list[DiferenciaOut]


class DetalleLiquidacionOut(_Base):
    concepto: Literal["sena", "pago_presupuesto", "devolucion_sena"]
    cantidad: int
    total: Dinero


class MedioLiquidacionOut(_Base):
    medio: Literal["mercadopago", "transferencia"]
    ingresos: Dinero
    egresos: Dinero
    neto: Dinero
    detalle: list[DetalleLiquidacionOut]


class LiquidacionOut(_Base):
    desde: date
    hasta: date
    medios: list[MedioLiquidacionOut]
    total_ingresos: Dinero
    total_egresos: Dinero
    total_neto: Dinero
    dias_sin_cierre: list[date]


# --- Pendientes de la seña (grupo 4) ------------------------------------------------------------------------

Referencia = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=64)]


class DevolucionIn(_Base):
    """El importe lo fija el sistema: un monto enviado da 422. La fecha, si viene, debe traer zona horaria."""

    referencia: Referencia
    fecha: datetime | None = None

    @field_validator("fecha")
    @classmethod
    def _con_zona(cls, v: datetime | None) -> datetime | None:
        if v is not None and (v.tzinfo is None or v.utcoffset() is None):
            raise ValueError("fecha debe incluir la zona horaria (por ejemplo -03:00)")
        return v


class PendienteOut(_Base):
    tipo: Literal["revision", "sena", "excedente_mp"]
    id: int
    pago_id: int
    turno_id: int
    estado_turno: str
    medio: Literal["mercadopago", "transferencia"]
    importe: Dinero | None
    importe_a_verificar: bool
    mp_payment_id: str | None
    pendiente_desde: datetime


class RechazoOut(_Base):
    pago_id: int
    turno_id: int
    estado_pago: str
    estado_turno: str
    importe: Dinero


class DevolucionOut(_Base):
    id: int
    tipo: Literal["sena", "excedente_mp"]
    pago_id: int
    turno_id: int
    importe: Dinero | None
    reembolsado_en: datetime
    referencia: str
