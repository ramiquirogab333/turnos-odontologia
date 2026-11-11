"""Esquemas de los indicadores del panel (C-12, R15): ``extra="forbid"``; solo cantidades, minutos, importes y nombres
de sillones y profesionales, nunca datos de pacientes (R19). Porcentajes e importes como texto decimal (R4)."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, PlainSerializer, model_validator

Decimal2 = Annotated[Decimal, PlainSerializer(lambda v: f"{v:.2f}", return_type=str, when_used="json")]
MAX_DIAS_OCUPACION = 31


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OcupacionQuery(_Base):
    """``desde`` y ``hasta`` inclusivos (hasta 31 días); ``sillon_id`` opcional."""

    desde: date
    hasta: date
    sillon_id: int | None = None

    @model_validator(mode="after")
    def _rango(self) -> "OcupacionQuery":
        if self.hasta < self.desde:
            raise ValueError("hasta no puede ser anterior a desde")
        if (self.hasta - self.desde).days >= MAX_DIAS_OCUPACION:
            raise ValueError(f"el rango no puede superar {MAX_DIAS_OCUPACION} días")
        return self


class OcupacionDiaOut(_Base):
    dia: date
    minutos_ocupados: int
    minutos_atencion: int
    porcentaje: Decimal2 | None
    turnos: int
    minutos_perdidos: int


class OcupacionSillonOut(_Base):
    sillon_id: int
    nombre: str
    estado: Literal["activo", "inactivo", "mantenimiento"]
    dias: list[OcupacionDiaOut]


class OcupacionOut(_Base):
    desde: date
    hasta: date
    sillones: list[OcupacionSillonOut]


class AusentismoProfesionalOut(_Base):
    profesional_id: int
    nombre: str
    atendidos: int
    ausentes: int
    tasa: Decimal2 | None
    sin_marcar: int


class RecuperoOut(_Base):
    """Señas retenidas (R9): turnos ``ausente`` cuya seña quedó ``no_reembolsado``."""

    senas_retenidas: int
    importe_retenido: Decimal2
    porcentaje: Decimal2 | None


class AusentismoOut(_Base):
    desde: date
    hasta: date
    atendidos: int
    ausentes: int
    tasa: Decimal2 | None
    sin_marcar: int
    por_profesional: list[AusentismoProfesionalOut]
    recupero: RecuperoOut
