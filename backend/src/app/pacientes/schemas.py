"""Esquemas Pydantic de pacientes y ficha (C-11, R15). ``extra="forbid"`` en todo; salida distinta por rol (O3)."""

import re
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.panel.schemas import Ref

_E164 = re.compile(r"^\+[1-9]\d{1,14}$")
_DNI = re.compile(r"^[0-9]{7,8}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_ANTECEDENTE = 2000


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PacienteCreate(_Base):
    """Alta (O1) y edición (``PUT``, reemplazo completo) de los datos administrativos."""

    nombre: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    apellido: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    dni: str
    telefono: str
    email: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None = None
    obra_social_id: int | None = None
    numero_afiliado: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)] | None = None

    @field_validator("dni")
    @classmethod
    def _dni(cls, v: str) -> str:
        if not _DNI.match(v):
            raise ValueError("dni debe tener 7 u 8 dígitos")
        return v

    @field_validator("telefono")
    @classmethod
    def _telefono(cls, v: str) -> str:
        if not _E164.match(v):
            raise ValueError("telefono debe tener formato E.164 (ej. +5491144445555)")
        return v

    @field_validator("email")
    @classmethod
    def _email(cls, v: str | None) -> str | None:
        if v is not None and not _EMAIL.match(v):
            raise ValueError("email inválido")
        return v


PacienteUpdate = PacienteCreate


class PacienteOut(_Base):
    """Vista completa (recepción y admin)."""

    id: int
    nombre: str
    apellido: str
    dni: str
    telefono: str
    email: str | None
    obra_social: Ref | None
    numero_afiliado: str | None


class PacienteVistaClinicaOut(_Base):
    """Vista de la odontóloga (O3): DNI y afiliado sí; teléfono y email nunca. Clase propia, no un ``exclude``."""

    id: int
    nombre: str
    apellido: str
    dni: str
    obra_social: Ref | None
    numero_afiliado: str | None


class VinculoTurnoUpdate(_Base):
    paciente_id: int


class VinculoTurnoOut(_Base):
    turno_id: int
    paciente_id: int


class TurnoHistoriaOut(_Base):
    turno_id: int
    inicio: datetime
    fin: datetime
    estado: str
    profesional: Ref
    tratamiento: Ref


class FichaUpdate(_Base):
    """Reemplazo de los antecedentes con la ``version`` leída (O6); 0 = ficha todavía no creada."""

    alergias: Annotated[str, Field(max_length=MAX_ANTECEDENTE)]
    medicacion: Annotated[str, Field(max_length=MAX_ANTECEDENTE)]
    antecedentes_medicos: Annotated[str, Field(max_length=MAX_ANTECEDENTE)]
    observaciones: Annotated[str, Field(max_length=MAX_ANTECEDENTE)]
    version: Annotated[int, Field(ge=0)]


class FichaOut(_Base):
    paciente_id: int
    alergias: str
    medicacion: str
    antecedentes_medicos: str
    observaciones: str
    version: int
    actualizado_por: int | None
    historia: list[TurnoHistoriaOut]
