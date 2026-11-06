"""Esquemas Pydantic de la seña (R15: validación en el borde, ``extra="forbid"``). Dinero como string decimal."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

MedioSena = Literal["mercadopago", "transferencia"]


class IniciarSenaRequest(BaseModel):
    """Cuerpo de POST /api/public/turnos/{id}/sena."""

    model_config = ConfigDict(extra="forbid")

    medio: MedioSena


class _SenaBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turno_id: int
    pago_id: int | None
    medio: MedioSena | None
    monto: Decimal
    vence_en: datetime | None
    texto_politica_reembolso: str
    referencia_externa: str | None
    checkout_url: str | None
    alias: str | None
    cbu: str | None
    titular: str | None
    referencia_concepto: str | None

    @field_serializer("monto")
    def _monto_como_texto(self, v: Decimal) -> str:
        return f"{v:.2f}"


class IniciarSenaResponse(_SenaBase):
    """201/200 de POST /sena: el pago pendiente y cómo completarlo."""

    estado: str


class EstadoSenaResponse(_SenaBase):
    """200 de GET /sena: estado del turno y del último pago. Sin datos de contacto."""

    estado_turno: str
    estado_pago: str | None
    vencida: bool
    medios_habilitados: list[str]
    # Datos del turno para mostrar la confirmación tras volver del checkout (sin datos de contacto).
    inicio: datetime
    fin: datetime
    tratamiento_nombre: str
    profesional_nombre: str


class ConfiguracionSenaUpdate(BaseModel):
    """Cuerpo de PUT /api/admin/config/sena (reemplazo completo). Espeja los CHECK de la migración 006."""

    model_config = ConfigDict(extra="forbid")

    sena_porcentaje: Decimal = Field(gt=0, le=100, max_digits=5, decimal_places=2)
    medios_habilitados: list[MedioSena] = Field(min_length=1)
    texto_politica_reembolso: str = Field(min_length=1, max_length=500)
    expiracion_mp_minutos: int = Field(ge=5, le=1440)
    expiracion_transferencia_minutos: int = Field(ge=5, le=4320)
    transferencia_alias: str | None = Field(default=None, min_length=6, max_length=40)
    transferencia_cbu: str | None = Field(default=None, pattern=r"^[0-9]{22}$")
    transferencia_titular: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("medios_habilitados")
    @classmethod
    def _sin_repetidos(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("medios_habilitados no admite repetidos")
        return v


class ConfiguracionSenaRead(ConfiguracionSenaUpdate):
    """Configuración vigente de la seña."""

    @field_serializer("sena_porcentaje")
    def _porcentaje_como_texto(self, v: Decimal) -> str:
        return f"{v:.2f}"


class AcreditacionResponse(BaseModel):
    """Resultado de acreditar una transferencia a mano."""

    model_config = ConfigDict(extra="forbid")

    pago_id: int
    turno_id: int
    efecto: str
    estado_pago: str
    estado_turno: str
