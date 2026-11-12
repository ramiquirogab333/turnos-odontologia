"""Esquemas Pydantic de la API de recordatorios del panel (C-09, R15: ``extra="forbid"`` en la entrada)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

EstadoVisible = Literal["pendiente", "enviado", "confirmado", "fallido"]
MotivoManual = Literal["numero_invalido", "sin_whatsapp", "otro"]
MotivoRecordatorio = Literal["sin_telefono", "numero_invalido", "sin_whatsapp", "otro", "error_proveedor"]


class MarcarFallidoIn(BaseModel):
    """Cuerpo de POST /{id}/fallido: solo los tres motivos que recepción puede declarar."""

    model_config = ConfigDict(extra="forbid")

    motivo: MotivoManual


class RecordatorioOut(BaseModel):
    """Un recordatorio vigente con lo que recepción necesita para avisar. El link se arma al responder (no se guarda)."""

    model_config = ConfigDict(extra="forbid")

    id: int
    turno_id: int
    estado: EstadoVisible
    motivo: MotivoRecordatorio | None
    turno_inicio: datetime
    profesional: str
    tratamiento: str
    contacto_nombre: str | None
    enviado_en: datetime | None
    intentos_fallidos: int
    link: str | None


class RecordatoriosOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[RecordatorioOut]
