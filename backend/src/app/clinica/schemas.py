"""Esquemas Pydantic de odontograma, presupuestos y pagos de presupuesto (C-11, R15).

``extra="forbid"`` en la entrada: el cliente no envía importes ni ``emitir_factura``. La salida distingue por rol con
clases distintas (``PresupuestoOut`` / ``PresupuestoVistaClinicaOut``), no con un ``exclude`` dinámico (O3).
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, StringConstraints, field_validator, model_validator

from app.clinica.odontograma import registro_valido
from app.panel.schemas import Ref

Dinero = Annotated[Decimal, PlainSerializer(lambda v: f"{v:.2f}", return_type=str, when_used="json")]
Motivo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=300)]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Odontograma ----------------------------------------------------------------------------------------------

class RegistroOdontogramaIn(_Base):
    pieza: int
    cara: Literal["O", "M", "D", "V", "L"] | None = None
    estado: str
    nota: Annotated[str, Field(min_length=1, max_length=500)] | None = None

    @model_validator(mode="after")
    def _coherente(self) -> "RegistroOdontogramaIn":
        if not registro_valido(self.pieza, self.cara, self.estado):
            raise ValueError("pieza FDI, cara o estado inválidos para el odontograma")
        return self


class LoteOdontogramaIn(_Base):
    registros: Annotated[list[RegistroOdontogramaIn], Field(min_length=1, max_length=64)]


class RegistroOdontogramaOut(_Base):
    id: int
    pieza: int
    cara: str | None
    estado: str
    nota: str | None
    registrado_por: int | None
    registrado_en: datetime


class LoteOdontogramaOut(_Base):
    registros: list[RegistroOdontogramaOut]


class PiezaVigenteOut(_Base):
    pieza: int
    estado_pieza: str | None
    caras: dict[str, str]


class OdontogramaVigenteOut(_Base):
    paciente_id: int
    piezas: list[PiezaVigenteOut]


class HistorialOdontogramaOut(_Base):
    registros: list[RegistroOdontogramaOut]
    siguiente_antes_de_id: int | None


class HistorialQuery(_Base):
    limite: Annotated[int, Field(ge=1, le=200)] = 50
    antes_de_id: Annotated[int, Field(ge=1)] | None = None


# --- Presupuestos ---------------------------------------------------------------------------------------------

class LineaIn(_Base):
    tratamiento_id: int
    cantidad: Annotated[int, Field(ge=1, le=99)]
    pieza: int | None = None
    cara: Literal["O", "M", "D", "V", "L"] | None = None

    @model_validator(mode="after")
    def _pieza_valida(self) -> "LineaIn":
        if self.pieza is not None and not registro_valido(self.pieza, None, "sano"):
            raise ValueError("pieza FDI inválida")
        if self.cara is not None and self.pieza is None:
            raise ValueError("la cara exige la pieza")
        return self


class PresupuestoCreate(_Base):
    """Alta y reemplazo de un borrador. ``obra_social_id`` ausente = la del paciente; ``null`` = particular."""

    lineas: Annotated[list[LineaIn], Field(min_length=1, max_length=50)]
    obra_social_id: int | None = None
    notas: Annotated[str, Field(max_length=1000)] = ""


PresupuestoUpdate = PresupuestoCreate


class TransicionIn(_Base):
    """Cuerpo (vacío) de presentar/aceptar/rechazar: cualquier campo, p. ej. ``emitir_factura``, es 422."""


class AnulacionIn(_Base):
    motivo: Motivo


class LineaOut(_Base):
    id: int
    orden: int
    tratamiento: Ref
    pieza: int | None
    cara: str | None
    cantidad: int
    precio_unitario: Dinero
    cobertura_porcentaje: Dinero
    arancel_diferencial: Dinero
    codigo_prestacion: str | None
    importe_bruto: Dinero
    importe_cobertura: Dinero
    importe_diferencial: Dinero
    importe_paciente: Dinero
    sin_cobertura: bool


class PagoOut(_Base):
    id: int
    presupuesto_id: int
    medio: str
    monto: Dinero
    estado: str
    fecha_cobro: datetime
    referencia: str | None
    registrado_por: int | None
    anulado_en: datetime | None
    anulado_motivo: str | None


class _PresupuestoBase(_Base):
    """Campos comunes. Las dos vistas son hermanas, NO subclase una de otra: con herencia, validar un
    ``PresupuestoOut`` como vista clínica devolvería la misma instancia y filtraría pagos y saldo."""

    id: int
    paciente_id: int
    obra_social: Ref | None
    estado: str
    subtotal: Dinero
    cobertura_total: Dinero
    diferencial_total: Dinero
    total_paciente: Dinero
    notas: str
    presentado_en: datetime | None
    resuelto_en: datetime | None
    anulado_en: datetime | None
    anulado_motivo: str | None
    created_at: datetime
    lineas: list[LineaOut]


class PresupuestoVistaClinicaOut(_PresupuestoBase):
    """Lo que ve la odontóloga (O3, O4): líneas y totales, nunca pagos ni saldo."""


class PresupuestoOut(_PresupuestoBase):
    """Vista completa (recepción y admin): suma pagos, total pagado y saldo."""

    pagos: list[PagoOut]
    total_pagado: Dinero
    saldo: Dinero


# --- Pagos de presupuesto -------------------------------------------------------------------------------------

class PagoCreate(_Base):
    medio: Literal["mercadopago", "transferencia"]
    monto: Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
    fecha_cobro: datetime | None = None
    referencia: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)] | None = None

    @field_validator("fecha_cobro")
    @classmethod
    def _con_zona(cls, v: datetime | None) -> datetime | None:
        if v is not None and (v.tzinfo is None or v.utcoffset() is None):
            raise ValueError("fecha_cobro debe incluir la zona horaria (por ejemplo -03:00)")
        return v


class PagoRegistradoOut(_Base):
    pago: PagoOut
    total_pagado: Dinero
    saldo: Dinero


class PagosPresupuestoOut(_Base):
    pagos: list[PagoOut]
    total_pagado: Dinero
    saldo: Dinero
