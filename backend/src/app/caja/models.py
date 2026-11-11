"""Modelos del cierre de caja (C-12; R4, R6). DDL canónico en la migración 009 (R14).

El cierre es una foto: se crea una vez y solo cambia de ``vigente`` a ``anulado`` (un trigger de la base lo garantiza).
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.core import Usuario  # noqa: F401  (resuelve la FK usuario.id en el metadata)

ESTADOS_CIERRE = ("vigente", "anulado")
CONCEPTOS_CAJA = ("sena", "pago_presupuesto", "devolucion_sena")
MEDIOS_CAJA = ("mercadopago", "transferencia")


class CierreCaja(Base):
    """Cierre de la caja de un día terminado de la clínica (un vigente por día)."""

    __tablename__ = "cierre_caja"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    dia: Mapped[date] = mapped_column(Date, nullable=False)
    estado: Mapped[str] = mapped_column(Text, nullable=False, default="vigente", server_default="vigente")
    total_ingresos: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total_egresos: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total_neto: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)
    cerrado_por: Mapped[int | None] = mapped_column(
        ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    cerrado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    anulado_por: Mapped[int | None] = mapped_column(
        ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    anulado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    anulado_motivo: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("total_neto = total_ingresos - total_egresos", name="ck_cierre_caja_neto"),
        Index("uq_cierre_caja_dia_vigente", "dia", unique=True, postgresql_where=text("estado = 'vigente'")),
        Index("ix_cierre_caja_dia", "dia"),
    )


class CierreCajaLinea(Base):
    """Una fila por concepto y medio del cierre, con cantidad y total."""

    __tablename__ = "cierre_caja_linea"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    cierre_id: Mapped[int] = mapped_column(ForeignKey("cierre_caja.id", ondelete="RESTRICT"), nullable=False)
    concepto: Mapped[str] = mapped_column(Text, nullable=False)
    medio: Mapped[str] = mapped_column(Text, nullable=False)
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    __table_args__ = (
        UniqueConstraint("cierre_id", "concepto", "medio", name="uq_cierre_caja_linea"),  # también cubre la FK (R6)
    )
