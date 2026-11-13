"""Core domain models for patients, availability, auth/roles, audit and coverage (C-02, R4, R6, R13)."""

from datetime import datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    Text,
    text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import ActiveMixin, Base, TimestampMixin


class ObraSocial(Base, ActiveMixin, TimestampMixin):
    """Obras sociales y prepagas aceptadas en el consultorio."""

    __tablename__ = "obra_social"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    codigo: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    sigla: Mapped[str] = mapped_column(Text, nullable=False, default="")

    __table_args__ = (
        CheckConstraint("LENGTH(codigo) BETWEEN 2 AND 30", name="ck_obra_social_codigo_len"),
        CheckConstraint("LENGTH(nombre) BETWEEN 2 AND 120", name="ck_obra_social_nombre_len"),
    )


class Paciente(Base, ActiveMixin, TimestampMixin):
    """Paciente del consultorio odontológico con DNI obligatorio y teléfono E.164."""

    __tablename__ = "paciente"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    apellido: Mapped[str] = mapped_column(Text, nullable=False)
    dni: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    telefono: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    obra_social_id: Mapped[int | None] = mapped_column(
        ForeignKey("obra_social.id", ondelete="SET NULL"), nullable=True, index=True
    )
    numero_afiliado: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("LENGTH(nombre) BETWEEN 1 AND 100", name="ck_paciente_nombre_len"),
        CheckConstraint("LENGTH(apellido) BETWEEN 1 AND 100", name="ck_paciente_apellido_len"),
        CheckConstraint("dni ~ '^[0-9]{7,8}$'", name="ck_paciente_dni_format"),
        CheckConstraint("LENGTH(telefono) BETWEEN 8 AND 25", name="ck_paciente_telefono_len"),
    )


class Rol(Base):
    """Roles de acceso al sistema (RBAC: admin, odontologo, recepcion)."""

    __tablename__ = "rol"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    nombre: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False, default="")

    __table_args__ = (
        CheckConstraint("nombre IN ('admin', 'odontologo', 'recepcion')", name="ck_rol_nombre"),
    )


class Usuario(Base, ActiveMixin, TimestampMixin):
    """Usuarios autenticables del panel interno."""

    __tablename__ = "usuario"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    nombre_completo: Mapped[str] = mapped_column(Text, nullable=False)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    profesional_id: Mapped[int | None] = mapped_column(
        ForeignKey("profesional.id", ondelete="SET NULL"), nullable=True, index=True
    )

    __table_args__ = (
        CheckConstraint("LENGTH(email) BETWEEN 5 AND 120", name="ck_usuario_email_len"),
        CheckConstraint("LENGTH(nombre_completo) BETWEEN 2 AND 120", name="ck_usuario_nombre_len"),
    )


class UsuarioRol(Base):
    """Asignación de roles a usuarios."""

    __tablename__ = "usuario_rol"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rol_id: Mapped[int] = mapped_column(
        ForeignKey("rol.id", ondelete="CASCADE"), nullable=False, index=True
    )

    __table_args__ = (
        UniqueConstraint("usuario_id", "rol_id", name="uq_usuario_rol"),
    )


class Disponibilidad(Base, ActiveMixin, TimestampMixin):
    """Franjas horarias habituales de atención por profesional y día de la semana."""

    __tablename__ = "disponibilidad"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    profesional_id: Mapped[int] = mapped_column(
        ForeignKey("profesional.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dia_semana: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=Lunes, 6=Domingo
    hora_inicio: Mapped[time] = mapped_column(Time, nullable=False)
    hora_fin: Mapped[time] = mapped_column(Time, nullable=False)
    sillon_defecto_id: Mapped[int | None] = mapped_column(
        ForeignKey("sillon.id", ondelete="SET NULL"), nullable=True, index=True
    )

    __table_args__ = (
        CheckConstraint("dia_semana BETWEEN 0 AND 6", name="ck_disponibilidad_dia_semana"),
        CheckConstraint("hora_fin > hora_inicio", name="ck_disponibilidad_horas"),
    )


class Nomenclador(Base):
    """Cobertura de prestaciones y aranceles según obra social."""

    __tablename__ = "nomenclador"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    obra_social_id: Mapped[int] = mapped_column(
        ForeignKey("obra_social.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tratamiento_id: Mapped[int] = mapped_column(
        ForeignKey("tratamiento.id", ondelete="CASCADE"), nullable=False, index=True
    )
    codigo_prestacion: Mapped[str] = mapped_column(Text, nullable=False)
    cobertura_porcentaje: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("100.00"))
    arancel_diferencial: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))

    __table_args__ = (
        CheckConstraint("cobertura_porcentaje BETWEEN 0 AND 100", name="ck_nomenclador_cobertura"),
        CheckConstraint("arancel_diferencial >= 0", name="ck_nomenclador_arancel_no_neg"),
        UniqueConstraint("obra_social_id", "tratamiento_id", name="uq_nomenclador_os_tratamiento"),
    )


class RegistroAuditoria(Base):
    """Auditoría de acciones sobre entidades sensibles y accesos (RN-GL-01)."""

    __tablename__ = "registro_auditoria"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    accion: Mapped[str] = mapped_column(Text, nullable=False)
    entidad: Mapped[str] = mapped_column(Text, nullable=False)
    entidad_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    datos_antes: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    datos_despues: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    ip: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=func.now(),
        index=True,
    )

    __table_args__ = (
        CheckConstraint("LENGTH(accion) BETWEEN 2 AND 50", name="ck_auditoria_accion_len"),
        CheckConstraint("LENGTH(entidad) BETWEEN 2 AND 50", name="ck_auditoria_entidad_len"),
        CheckConstraint("ip IS NULL OR LENGTH(ip) <= 45", name="ck_auditoria_ip_len"),
        Index("ix_registro_auditoria_entidad", "entidad", "entidad_id", text("created_at DESC")),
    )
