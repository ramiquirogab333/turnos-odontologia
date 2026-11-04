"""Esquemas Pydantic para endpoints públicos (R15: validación en el borde).

- ConfigDict(extra="forbid") en todos los modelos de entrada/salida.
- field_validator de teléfono E.164 (código de país + número, sin espacios).
"""

import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator, model_validator

from app.shared.settings import get_settings

MAX_RANGO_DIAS = 31
MAX_NOMBRE = 200

_E164_RE = re.compile(r"^\+[1-9]\d{1,14}$")


def _validar_telefono_e164(valor: str, campo: str = "telefono") -> str:
    if not _E164_RE.match(valor):
        raise ValueError(f"{campo} debe tener formato E.164 (ej. +5491144445555)")
    return valor


class DisponibilidadPublicaQuery(BaseModel):
    """Query params de GET /api/public/disponibilidad."""

    model_config = ConfigDict(extra="forbid")

    profesional_id: int
    tratamiento_id: int
    desde: date
    hasta: date

    @model_validator(mode="after")
    def _rango_coherente(self) -> "DisponibilidadPublicaQuery":
        if self.hasta < self.desde:
            raise ValueError("hasta no puede ser anterior a desde")
        if self.hasta - self.desde > timedelta(days=MAX_RANGO_DIAS):
            raise ValueError(f"el rango máximo es de {MAX_RANGO_DIAS} días")
        return self


class DisponibilidadPublicaSlot(BaseModel):
    """Un slot libre con profesional y sillón asignado."""

    model_config = ConfigDict(extra="forbid")

    inicio: datetime
    fin: datetime
    profesional_id: int
    sillon_id: int


class DisponibilidadPublicaResponse(BaseModel):
    """Respuesta de GET /api/public/disponibilidad."""

    model_config = ConfigDict(extra="forbid")

    slots: list[DisponibilidadPublicaSlot]


class ReservaPublicaRequest(BaseModel):
    """Payload de POST /api/public/turnos (reserva pública sin autenticación)."""

    model_config = ConfigDict(extra="forbid")

    nombre: str
    telefono: str
    tratamiento_id: int
    profesional_id: int
    inicio: datetime

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v: str) -> str:
        v = v.strip()
        if not (1 <= len(v) <= MAX_NOMBRE):
            raise ValueError(f"nombre debe tener entre 1 y {MAX_NOMBRE} caracteres")
        return v

    @field_validator("telefono")
    @classmethod
    def _telefono_e164(cls, v: str) -> str:
        return _validar_telefono_e164(v)

    @field_validator("inicio")
    @classmethod
    def _inicio_tz_aware_y_futuro(cls, value: datetime) -> datetime:
        """Naive = hora local de la clínica (APP_TZ); rechaza inicio pasado con 422."""
        if value.tzinfo is None:
            value = value.replace(tzinfo=ZoneInfo(get_settings().app_tz))
        if value <= datetime.now(timezone.utc):
            raise ValueError("inicio debe ser futuro")
        return value


class ReservaPublicaResponse(BaseModel):
    """Respuesta 201 de POST /api/public/turnos."""

    model_config = ConfigDict(extra="forbid")

    turno_id: int
    codigo_gestion: str
    estado: str
    inicio: datetime
    fin: datetime


class ReservaConflictoBody(BaseModel):
    """Cuerpo del 409 Conflict con motivo y alternativas libres."""

    model_config = ConfigDict(extra="forbid")

    detail: str
    motivo: Literal["profesional", "sillon"]
    alternativas: list[dict]


class TratamientoPublico(BaseModel):
    """Tratamiento visible en el paso 1 del wizard (sin datos internos)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    duracion_minutos: int
    precio_base: Decimal

    @field_serializer("precio_base")
    def _precio_como_texto(self, v: Decimal) -> str:
        return str(v)


class ProfesionalPublico(BaseModel):
    """Profesional elegible por el paciente; no expone la matrícula."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    especialidad: str
