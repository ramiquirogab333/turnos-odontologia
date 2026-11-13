"""Esquemas de la plataforma (C-13, R15): consulta de auditoría y su respuesta. ``extra="forbid"`` en la entrada."""

from datetime import date, datetime, timedelta
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.plataforma.tipos_auditoria import TIPOS

DIAS_POR_DEFECTO = 7
MAX_DIAS_RANGO = 366


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AuditoriaQuery(_Base):
    """Query params de ``GET /api/panel/auditoria``. Fechas locales de la clínica; por defecto los últimos 7 días."""

    desde: date | None = None
    hasta: date | None = None
    entidad: Annotated[str | None, Field(min_length=2, max_length=50)] = None
    entidad_id: Annotated[str | None, Field(min_length=1, max_length=50)] = None
    usuario_id: Annotated[int | None, Field(gt=0)] = None
    tipo: str | None = None
    por_pagina: Annotated[int, Field(ge=1, le=100)] = 50
    cursor: Annotated[str | None, Field(min_length=1, max_length=300)] = None

    @field_validator("tipo")
    @classmethod
    def _tipo_del_catalogo(cls, v: str | None) -> str | None:
        if v is not None and v not in TIPOS:
            raise ValueError(f"tipo inválido; los válidos son: {', '.join(sorted(TIPOS))}")
        return v

    @model_validator(mode="after")
    def _rango_coherente(self) -> "AuditoriaQuery":
        if self.desde is not None and self.hasta is not None:
            self._validar_rango(self.desde, self.hasta)
        return self

    @staticmethod
    def _validar_rango(desde: date, hasta: date) -> None:
        if desde > hasta:
            raise ValueError("desde no puede ser posterior a hasta")
        if (hasta - desde).days > MAX_DIAS_RANGO:
            raise ValueError(f"el rango no puede superar {MAX_DIAS_RANGO} días")

    def rango(self, hoy: date) -> tuple[date, date]:
        """Rango efectivo: lo que falte se completa con ``hoy`` o 7 días antes de ``hasta``. ``ValueError`` si es incoherente."""
        hasta = self.hasta or hoy
        desde = self.desde or hasta - timedelta(days=DIAS_POR_DEFECTO - 1)
        self._validar_rango(desde, hasta)
        return desde, hasta

    def filtros_auditables(self, desde: date, hasta: date) -> dict[str, Any]:
        """Filtros para el registro ``lectura_auditoria``: solo fechas, ids y códigos (nunca texto libre)."""
        filtros: dict[str, Any] = {"desde": desde.isoformat(), "hasta": hasta.isoformat(), "por_pagina": self.por_pagina,
                                   "con_cursor": self.cursor is not None}
        for campo in ("entidad", "entidad_id", "usuario_id", "tipo"):
            if (valor := getattr(self, campo)) is not None:
                filtros[campo] = valor
        return filtros


class UsuarioRef(_Base):
    id: int
    nombre_completo: str


class RegistroAuditoriaOut(_Base):
    id: int
    fecha_hora: datetime
    usuario: UsuarioRef | None
    accion: str
    tipo: str
    tipo_etiqueta: str
    entidad: str
    entidad_id: str | None
    datos_antes: Any | None
    datos_despues: Any | None
    ip: str | None


class AuditoriaPagina(_Base):
    items: list[RegistroAuditoriaOut]
    siguiente: str | None


class UsuarioDirectorioOut(_Base):
    id: int
    nombre_completo: str
    activo: bool
