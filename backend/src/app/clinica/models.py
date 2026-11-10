"""Modelos clínicos y de presupuestos (C-11; R4, R6). DDL canónico en la migración 008 (R14)."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.core import Nomenclador, ObraSocial, Paciente, Usuario  # noqa: F401  (FK en el metadata)
from app.turnos.models import Tratamiento  # noqa: F401

ESTADOS_PRESUPUESTO = ("borrador", "presentado", "aceptado", "rechazado", "anulado")
MEDIOS_PAGO_PRESUPUESTO = ("mercadopago", "transferencia")
ESTADOS_PAGO_PRESUPUESTO = ("registrado", "anulado")


class OdontogramaRegistro(Base):
    """Un hallazgo del odontograma. Solo se agregan registros: el estado vigente se deriva (O7)."""

    __tablename__ = "odontograma_registro"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("paciente.id", ondelete="RESTRICT"), nullable=False)
    pieza: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    cara: Mapped[str | None] = mapped_column(Text, nullable=True)
    estado: Mapped[str] = mapped_column(Text, nullable=False)
    nota: Mapped[str | None] = mapped_column(Text, nullable=True)
    registrado_por: Mapped[int | None] = mapped_column(
        ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    registrado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("ix_odontograma_paciente_historial", "paciente_id", text("registrado_en DESC"), text("id DESC")),
    )


class Presupuesto(Base):
    """Presupuesto de tratamientos de un paciente; importes con la cobertura de la obra social (O9-O11)."""

    __tablename__ = "presupuesto"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("paciente.id", ondelete="RESTRICT"), nullable=False)
    obra_social_id: Mapped[int | None] = mapped_column(
        ForeignKey("obra_social.id", ondelete="RESTRICT"), nullable=True, index=True)
    estado: Mapped[str] = mapped_column(Text, nullable=False, default="borrador", server_default="borrador")
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    cobertura_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    diferencial_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    total_paciente: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    notas: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    creado_por: Mapped[int | None] = mapped_column(
        ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    presentado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resuelto_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    anulado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    anulado_motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("total_paciente = subtotal - cobertura_total + diferencial_total", name="ck_presupuesto_total"),
        Index("ix_presupuesto_paciente", "paciente_id", text("created_at DESC")),
    )


class PresupuestoLinea(Base):
    """Línea con el snapshot de precio, cobertura y diferencial vigentes al calcular."""

    __tablename__ = "presupuesto_linea"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    presupuesto_id: Mapped[int] = mapped_column(ForeignKey("presupuesto.id", ondelete="CASCADE"), nullable=False)
    orden: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    tratamiento_id: Mapped[int] = mapped_column(
        ForeignKey("tratamiento.id", ondelete="RESTRICT"), nullable=False, index=True)
    nomenclador_id: Mapped[int | None] = mapped_column(
        ForeignKey("nomenclador.id", ondelete="SET NULL"), nullable=True, index=True)
    codigo_prestacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    pieza: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    cara: Mapped[str | None] = mapped_column(Text, nullable=True)
    cantidad: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    precio_unitario: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    cobertura_porcentaje: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("0.00"))
    arancel_diferencial: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    importe_bruto: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    importe_cobertura: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    importe_diferencial: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    importe_paciente: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    __table_args__ = (
        UniqueConstraint("presupuesto_id", "orden", name="uq_presupuesto_linea_orden"),
    )


class PagoPresupuesto(Base):
    """Cobro registrado a mano contra un presupuesto aceptado. Se anula, nunca se borra (O12)."""

    __tablename__ = "pago_presupuesto"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    presupuesto_id: Mapped[int] = mapped_column(
        ForeignKey("presupuesto.id", ondelete="RESTRICT"), nullable=False, index=True)
    medio: Mapped[str] = mapped_column(Text, nullable=False)
    monto: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    estado: Mapped[str] = mapped_column(Text, nullable=False, default="registrado", server_default="registrado")
    fecha_cobro: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    referencia: Mapped[str | None] = mapped_column(Text, nullable=True)
    registrado_por: Mapped[int | None] = mapped_column(
        ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    anulado_por: Mapped[int | None] = mapped_column(
        ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    anulado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    anulado_motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("uq_pago_presupuesto_medio_referencia", "medio", "referencia", unique=True,
              postgresql_where=text("referencia IS NOT NULL AND estado = 'registrado'")),
    )
