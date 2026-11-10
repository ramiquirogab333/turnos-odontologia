"""Modelo de la ficha clínica (C-11; R4, R6). DDL canónico en la migración 008 (R14)."""

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.core import Paciente, Usuario  # noqa: F401  (resuelven las FK en el metadata)


class Ficha(Base):
    """Antecedentes clínicos 1:1 con el paciente, con control de versión optimista (O6)."""

    __tablename__ = "ficha"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    paciente_id: Mapped[int] = mapped_column(
        ForeignKey("paciente.id", ondelete="RESTRICT"), nullable=False, unique=True)
    alergias: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    medicacion: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    antecedentes_medicos: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    observaciones: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    actualizado_por: Mapped[int | None] = mapped_column(
        ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_ficha_version"),
        CheckConstraint("LENGTH(alergias) <= 2000", name="ck_ficha_alergias_len"),
        CheckConstraint("LENGTH(medicacion) <= 2000", name="ck_ficha_medicacion_len"),
        CheckConstraint("LENGTH(antecedentes_medicos) <= 2000", name="ck_ficha_antecedentes_len"),
        CheckConstraint("LENGTH(observaciones) <= 2000", name="ck_ficha_observaciones_len"),
    )
