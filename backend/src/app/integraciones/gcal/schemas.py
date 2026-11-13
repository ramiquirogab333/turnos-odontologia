"""Esquemas Pydantic de entrada y salida de Google Calendar (C-10, R15). Nunca un token ni un dato del paciente."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

EstadoConexionOut = Literal["sin_conectar", "pendiente", "activa", "revocada", "desconectada"]
TipoConflicto = Literal["movido_en_google", "borrado_en_google", "solapa_evento_externo"]
AccionConflicto = Literal["restaurar_en_google", "desvincular", "revisado"]
EstadoConflicto = Literal["abierto", "resuelto"]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConexionOut(_Base):
    profesional_id: int
    profesional_nombre: str
    estado: EstadoConexionOut
    cuenta_email: str | None
    ultima_sync_ok_en: datetime | None
    conflictos_abiertos: int
    indicacion: str | None


class IniciarOut(_Base):
    url_autorizacion: str


class ConflictoOut(_Base):
    id: int
    tipo: TipoConflicto
    estado: EstadoConflicto
    criterio: str
    turno_id: int
    profesional_id: int
    profesional_nombre: str
    tratamiento: str
    sistema_inicio: datetime
    sistema_fin: datetime
    google_inicio: datetime | None
    google_fin: datetime | None
    acciones: list[AccionConflicto]
    resolucion: str | None
    detectado_en: datetime
    resuelto_en: datetime | None


class ResolverIn(_Base):
    accion: AccionConflicto
