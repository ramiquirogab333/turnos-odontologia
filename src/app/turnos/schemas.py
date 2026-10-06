"""Pydantic schemas for turnos (R15: validation at the edge)."""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


class TurnoCreate(BaseModel):
    """Identity-free creation payload (D9).

    `fin` is NOT accepted: any client-sent `fin` is rejected with 422
    (``extra="forbid"``) and the server derives it as
    ``inicio + tratamiento.duracion_minutos`` (RN-TU-04).
    """

    model_config = ConfigDict(extra="forbid")

    profesional_id: int
    sillon_id: int
    tratamiento_id: int
    inicio: datetime

    @field_validator("inicio")
    @classmethod
    def inicio_tz_aware_y_futuro(cls, value: datetime) -> datetime:
        """Assume UTC when naive; reject past `inicio` with 422 (Q3)."""
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        if value <= datetime.now(timezone.utc):
            raise ValueError("inicio debe ser futuro")
        return value


class TurnoRead(BaseModel):
    """Persisted turno as returned with 201."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    profesional_id: int
    sillon_id: int
    tratamiento_id: int
    inicio: datetime
    fin: datetime
    estado: str


class ConflictoSolape(BaseModel):
    """Body of a 409 overlap rejection (D5)."""

    detail: str
    motivo: Literal["profesional", "sillon"]


class HealthRead(BaseModel):
    """Body of GET /api/health."""

    status: str
    db: str
