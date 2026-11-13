"""Esquemas Pydantic del panel (R15: validación en el borde; ``extra="forbid"`` en todo)."""

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.panel.acciones import Accion

MAX_NOMBRE = 200
_E164 = re.compile(r"^\+[1-9]\d{1,14}$")


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgendaQuery(_Base):
    """Query params de ``GET /api/panel/agenda``."""

    vista: Literal["dia", "semana"]
    fecha: date
    profesional_id: int | None = None
    sillon_id: int | None = None


class Ref(_Base):
    id: int
    nombre: str


class TratamientoRef(_Base):
    id: int
    nombre: str
    duracion_minutos: int


class SenaAgenda(_Base):
    """Estado de la última seña del turno; el monto viaja como string decimal (R4)."""

    estado: str
    monto: Decimal

    @field_serializer("monto")
    def _monto_como_texto(self, v: Decimal) -> str:
        return f"{v:.2f}"


class CalendarioTurno(_Base):
    """Estado del evento de Google Calendar del turno y si tiene un conflicto abierto (C-10)."""

    estado: Literal["sin_evento", "pendiente", "sincronizado", "desvinculado"] = "sin_evento"
    conflicto_abierto: bool = False


class TurnoAgenda(_Base):
    id: int
    inicio: datetime
    fin: datetime
    estado: str
    bloquea_agenda: bool
    origen: str
    profesional: Ref
    sillon: Ref
    tratamiento: TratamientoRef
    paciente_nombre: str | None
    paciente_telefono: str | None
    sena: SenaAgenda | None
    vence_en: datetime | None
    acciones: list[Accion]
    calendario: CalendarioTurno = Field(default_factory=CalendarioTurno)


class OcupadoGoogle(_Base):
    """Franja ocupada en el Google Calendar de la profesional (C-10, O19): sin título ni otro dato del evento."""

    profesional_id: int
    inicio: datetime
    fin: datetime


class AgendaResponse(_Base):
    vista: Literal["dia", "semana"]
    desde: date
    hasta: date
    turnos: list[TurnoAgenda]
    ocupados_google: list[OcupadoGoogle] = Field(default_factory=list)


class OpcionesResponse(_Base):
    profesionales: list[Ref]
    sillones: list[Ref]
    tratamientos: list[TratamientoRef]
    puede_escribir: bool


class TurnoManualCreate(_Base):
    """Alta manual (O8): contacto del turno, sin ``Paciente``. ``fin`` y ``estado`` no se aceptan (RN-TU-04, O7)."""

    profesional_id: int
    tratamiento_id: int
    inicio: datetime
    nombre: str
    telefono: str
    sillon_id: int | None = None

    @field_validator("inicio")
    @classmethod
    def _inicio_con_zona(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError("inicio debe incluir la zona horaria (por ejemplo -03:00)")
        return v

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v: str) -> str:
        v = v.strip()
        if not 1 <= len(v) <= MAX_NOMBRE:
            raise ValueError(f"nombre debe tener entre 1 y {MAX_NOMBRE} caracteres")
        return v

    @field_validator("telefono")
    @classmethod
    def _telefono(cls, v: str) -> str:
        if not _E164.match(v):
            raise ValueError("telefono debe tener formato E.164 (ej. +5491144445555)")
        return v


class TurnoManualCreado(_Base):
    """Respuesta 201 del alta manual. El código de gestión se devuelve SOLO acá (O11)."""

    id: int
    inicio: datetime
    fin: datetime
    estado: Literal["reservado"]
    origen: Literal["manual"]
    profesional_id: int
    sillon_id: int
    tratamiento_id: int
    codigo_gestion: str
    # C-10 (O10): el horario figura ocupado en el Google Calendar de la profesional; el turno se creó igual.
    aviso_google_calendar: bool = False


MotivoDeshacer = Literal["turno_equivocado", "paciente_no_asistio", "otro"]


class DeshacerAtendidoIn(_Base):
    """Motivo de un catálogo: se puede auditar sin riesgo de texto libre con datos personales (C-12, D6)."""

    motivo: MotivoDeshacer


class CambioEstadoResponse(_Base):
    turno_id: int
    estado: str
    estado_sena: str | None


class ErrorPanelBody(_Base):
    """Cuerpo de un rechazo del panel: ``motivo`` estable para que la pantalla decida qué decir."""

    detail: str
    motivo: str
    limite_cambios: datetime | None = None
    habilitado_desde: datetime | None = None
    limite_correccion: datetime | None = None  # C-12: último instante para deshacer un atendido
