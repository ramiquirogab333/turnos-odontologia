"""Modelos de la seña (C-06; R4, R6). DDL canónico en la migración 006_sena_pagos (R14)."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.core import Usuario  # noqa: F401  (resuelve la FK usuario.id en el metadata)
from app.turnos.models import Turno  # noqa: F401  (resuelve la FK turno.id en el metadata)

MEDIOS_SENA = ("mercadopago", "transferencia")
ESTADOS_PAGO = ("pendiente", "acreditado", "vencido", "no_reembolsado", "a_reembolsar", "en_revision")


class ConfiguracionSena(Base):
    """Configuración singleton (id = 1) editable por el admin (RN-SN-03, RN-SN-07)."""

    __tablename__ = "configuracion_sena"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    sena_porcentaje: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    medios_habilitados: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    texto_politica_reembolso: Mapped[str] = mapped_column(Text, nullable=False)
    expiracion_mp_minutos: Mapped[int] = mapped_column(Integer, nullable=False)
    expiracion_transferencia_minutos: Mapped[int] = mapped_column(Integer, nullable=False)
    transferencia_alias: Mapped[str | None] = mapped_column(Text, nullable=True)
    transferencia_cbu: Mapped[str | None] = mapped_column(Text, nullable=True)
    transferencia_titular: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("id = 1", name="configuracion_sena_id_check"),
        CheckConstraint("sena_porcentaje > 0 AND sena_porcentaje <= 100", name="ck_config_sena_porcentaje"),
    )


class AprobacionPago(Base):
    """Cada pago aprobado de la pasarela, por su id (único): trazabilidad de sobrantes y de pagos en revisión."""

    __tablename__ = "pago_sena_aprobacion"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    pago_id: Mapped[int] = mapped_column(ForeignKey("pago_sena.id", ondelete="RESTRICT"), nullable=False)
    mp_payment_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    estado: Mapped[str] = mapped_column(Text, nullable=False)  # aplicado | en_revision | a_reembolsar
    monto_reportado: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    moneda_reportada: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("estado IN ('aplicado','en_revision','a_reembolsar')", name="ck_pago_sena_aprobacion_estado"),
        CheckConstraint("monto_reportado IS NULL OR monto_reportado >= 0", name="ck_pago_sena_aprobacion_monto"),
        Index("ix_pago_sena_aprobacion_pago", "pago_id"),  # R6
    )


class PagoSena(Base):
    """Seña de un turno; un solo pago activo (pendiente/acreditado) por turno."""

    __tablename__ = "pago_sena"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    turno_id: Mapped[int] = mapped_column(
        ForeignKey("turno.id", ondelete="RESTRICT"), nullable=False)
    medio: Mapped[str] = mapped_column(Text, nullable=False)
    monto: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    porcentaje_aplicado: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    estado: Mapped[str] = mapped_column(Text, nullable=False, default="pendiente", server_default="pendiente")
    referencia_externa: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    mp_payment_id: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    checkout_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    vence_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # RN-SN-09: lo que informó la pasarela cuando no coincidió con la seña (para que el admin lo revise).
    monto_reportado: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    moneda_reportada: Mapped[str | None] = mapped_column(Text, nullable=True)
    acreditado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acreditado_por_usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("medio IN ('mercadopago','transferencia')", name="ck_pago_sena_medio"),
        CheckConstraint("monto > 0", name="ck_pago_sena_monto"),
        CheckConstraint(
            "estado IN ('pendiente','acreditado','vencido','no_reembolsado','a_reembolsar','en_revision')",
            name="ck_pago_sena_estado"),
        Index("ix_pago_sena_turno", "turno_id"),  # R6
        Index("ix_pago_sena_acreditado_por", "acreditado_por_usuario_id"),  # R6
        Index("uq_pago_sena_activo", "turno_id", unique=True,
              postgresql_where="estado IN ('pendiente','acreditado')"),
        Index("ix_pago_sena_pendiente_vence", "vence_en", postgresql_where="estado = 'pendiente'"),
    )
