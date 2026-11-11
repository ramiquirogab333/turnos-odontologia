"""Esquemas del listado de pacientes (C-12, R15): ``extra="forbid"``; la consulta valida ``q`` y la paginación."""

import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.panel.schemas import Ref

MIN_Q = 2
MAX_Q = 60


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ListadoQuery(_Base):
    """Query params de ``GET /api/panel/pacientes/listado``. ``q`` se normaliza (espacios simples) antes de validar."""

    q: str | None = None
    pagina: Annotated[int, Field(ge=1)] = 1
    por_pagina: Annotated[int, Field(ge=1, le=50)] = 20
    con_ausencias: bool = False
    orden: Literal["apellido", "ausencias"] = "apellido"

    @field_validator("q")
    @classmethod
    def _normalizar(cls, v: str | None) -> str | None:
        if v is None:
            return None
        limpio = re.sub(r"\s+", " ", v).strip()
        if not limpio:
            return None
        if not MIN_Q <= len(limpio) <= MAX_Q:
            raise ValueError(f"q debe tener entre {MIN_Q} y {MAX_Q} caracteres")
        return limpio


class PacienteListadoOut(_Base):
    id: int
    nombre: str
    apellido: str
    dni: str
    telefono: str
    obra_social: Ref | None
    atendidos: int
    ausentes: int
    ultimo_turno: datetime | None


class ListadoOut(_Base):
    total: int
    pagina: int
    por_pagina: int
    pacientes: list[PacienteListadoOut]
