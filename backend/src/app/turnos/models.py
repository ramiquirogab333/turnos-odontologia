"""SQLAlchemy models (R4/R6). EXCLUDE anti-solape vive en la migracion 001 (R5/R14)."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, Computed, DateTime, ForeignKey, Identity, Index, Numeric, Text
from sqlalchemy.dialects.postgresql import TSTZRANGE
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


from app.models.base import Base


class Profesional(Base):
    """Odontologo que atiende turnos."""

    __tablename__ = "profesional"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    matricula: Mapped[str] = mapped_column(Text, nullable=False)
    especialidad: Mapped[str] = mapped_column(Text, nullable=False, default="")

    __table_args__ = (
        CheckConstraint("LENGTH(nombre) BETWEEN 1 AND 120", name="ck_profesional_nombre_len"),
        CheckConstraint("LENGTH(matricula) BETWEEN 1 AND 40", name="ck_profesional_matricula_len"),
        CheckConstraint("LENGTH(especialidad) <= 120", name="ck_profesional_especialidad_len"),
    )


class Sillon(Base):
    """Sillon/box donde se atiende."""

    __tablename__ = "sillon"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    estado: Mapped[str] = mapped_column(Text, nullable=False, default="activo")

    __table_args__ = (
        CheckConstraint("LENGTH(nombre) BETWEEN 1 AND 60", name="ck_sillon_nombre_len"),
        CheckConstraint("estado IN ('activo','inactivo','mantenimiento')", name="ck_sillon_estado"),
    )


class Tratamiento(Base):
    """Prestacion con duracion (determina el fin del turno) y precio base."""

    __tablename__ = "tratamiento"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    duracion_minutos: Mapped[int] = mapped_column(nullable=False)
    precio_base: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    __table_args__ = (
        CheckConstraint("LENGTH(nombre) BETWEEN 1 AND 120", name="ck_tratamiento_nombre_len"),
        CheckConstraint("duracion_minutos > 0", name="ck_tratamiento_duracion_pos"),
        CheckConstraint("precio_base >= 0", name="ck_tratamiento_precio_no_neg"),
    )


class Turno(Base):
    """Turno agendado. El anti-solape lo garantizan los EXCLUDE de la migracion 001."""

    __tablename__ = "turno"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    profesional_id: Mapped[int] = mapped_column(
        ForeignKey("profesional.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    sillon_id: Mapped[int] = mapped_column(
        ForeignKey("sillon.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    tratamiento_id: Mapped[int] = mapped_column(
        ForeignKey("tratamiento.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    paciente_id: Mapped[int | None] = mapped_column(
        ForeignKey("paciente.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fin: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    estado: Mapped[str] = mapped_column(Text, nullable=False, default="reservado")
    # Reserva pública (C-05): código de gestión + contacto del solicitante, sin crear Paciente
    # (Paciente exige DNI, que la reserva pública no pide - RN-TU-06).
    codigo_gestion: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    contacto_nombre: Mapped[str | None] = mapped_column(Text, nullable=True)
    contacto_telefono: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Seña (C-06): vencimiento de la pre-reserva; obligatorio mientras el turno está en_espera.
    en_espera_vence_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # C-08: canal de alta (web = reserva pública; manual = recepción/admin en el panel; whatsapp = C-09).
    origen: Mapped[str] = mapped_column(Text, nullable=False, default="web", server_default="web")
    periodo: Mapped[Any] = mapped_column(
        TSTZRANGE, Computed("tstzrange(inicio, fin, '[)')", persisted=True)
    )

    __table_args__ = (
        CheckConstraint("fin > inicio", name="ck_turno_fin_after_inicio"),
        CheckConstraint(
            "estado IN ('reservado','confirmado','en_espera','cancelado','ausente','atendido')",
            name="ck_turno_estado",
        ),
        Index("ix_turno_profesional_inicio", "profesional_id", "inicio"),
        Index("ix_turno_sillon_inicio", "sillon_id", "inicio"),
        Index("ix_turno_paciente_inicio", "paciente_id", "inicio"),
        CheckConstraint(
            "estado <> 'en_espera' OR en_espera_vence_en IS NOT NULL", name="ck_turno_en_espera_vence"
        ),
        CheckConstraint("origen IN ('web', 'manual', 'whatsapp')", name="ck_turno_origen"),
        CheckConstraint(
            "codigo_gestion IS NULL OR LENGTH(codigo_gestion) BETWEEN 8 AND 64",
            name="ck_turno_codigo_gestion_len",
        ),
        CheckConstraint(
            "contacto_nombre IS NULL OR LENGTH(contacto_nombre) BETWEEN 1 AND 200",
            name="ck_turno_contacto_nombre_len",
        ),
        CheckConstraint(
            r"contacto_telefono IS NULL OR contacto_telefono ~ '^\+[1-9][0-9]{1,14}$'",
            name="ck_turno_contacto_telefono_e164",
        ),
    )
