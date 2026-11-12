"""Esquemas Pydantic de la gestión del turno (R15: ``extra="forbid"``). Dinero como string decimal (R4)."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, field_serializer

EstadoTurno = Literal["en_espera", "reservado", "confirmado", "cancelado", "ausente", "atendido"]
MotivoNoModificable = Literal["fuera_de_plazo", "turno_no_modificable", "sena_pendiente", "turno_iniciado"]
MotivoNoConfirmable = Literal["sena_pendiente", "turno_no_modificable", "turno_iniciado", "ya_confirmado"]


class ReprogramarRequest(BaseModel):
    """Cuerpo de POST /api/public/gestion/reprogramar: el nuevo inicio, con zona horaria."""

    model_config = ConfigDict(extra="forbid")

    inicio: AwareDatetime


class TratamientoGestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    nombre: str
    duracion_minutos: int


class ProfesionalGestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    nombre: str


class SenaGestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    monto: Decimal
    estado: str

    @field_serializer("monto")
    def _monto_como_texto(self, v: Decimal) -> str:
        return f"{v:.2f}"


class GestionTurnoResponse(BaseModel):
    """Datos para gestionar el turno. Nunca incluye el teléfono ni el nombre de contacto."""

    model_config = ConfigDict(extra="forbid")

    estado: EstadoTurno
    inicio: datetime
    fin: datetime
    tratamiento: TratamientoGestion
    profesional: ProfesionalGestion
    sena: SenaGestion | None
    limite_cambios: datetime
    puede_cancelar: bool
    puede_reprogramar: bool
    motivo_no_cancelable: MotivoNoModificable | None
    motivo_no_reprogramable: MotivoNoModificable | None
    puede_confirmar: bool
    motivo_no_confirmable: MotivoNoConfirmable | None
    texto_politica_reembolso: str


class CancelacionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estado: Literal["cancelado"]
    estado_sena: str | None


class ConfirmacionResponse(BaseModel):
    """Respuesta de POST /api/public/gestion/confirmar (C-09): el turno confirmado, en hora de la clínica."""

    model_config = ConfigDict(extra="forbid")

    estado: Literal["confirmado"]
    inicio: datetime
    fin: datetime


class ReprogramacionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estado: EstadoTurno
    inicio: datetime
    fin: datetime
    estado_sena: str | None


class ErrorGestionBody(BaseModel):
    """Cuerpo de los 409 ``fuera_de_plazo`` / ``turno_no_modificable`` / ``sena_pendiente``."""

    model_config = ConfigDict(extra="forbid")

    detail: str
    motivo: MotivoNoModificable
    limite_cambios: datetime | None = None
