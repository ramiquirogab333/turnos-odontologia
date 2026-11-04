"""Tests for Core Domain Models (C-02) - Strict TDD."""

from decimal import Decimal
import pytest
from sqlalchemy import BigInteger, Numeric, inspect
from sqlalchemy.orm import DeclarativeBase

from app.models.core import (
    Disponibilidad,
    Nomenclador,
    ObraSocial,
    Paciente,
    RegistroAuditoria,
    Rol,
    Usuario,
    UsuarioRol,
)
from app.turnos.models import Turno


def test_paciente_model_attributes_and_constraints():
    # Check DNI and Telefono required and mapped properly
    assert Paciente.__tablename__ == "paciente"
    assert hasattr(Paciente, "dni")
    assert hasattr(Paciente, "telefono")
    assert hasattr(Paciente, "nombre")
    assert hasattr(Paciente, "apellido")
    assert hasattr(Paciente, "obra_social_id")
    assert hasattr(Paciente, "created_at")
    assert hasattr(Paciente, "is_active")

    # DNI and telefono cannot be nullable
    assert Paciente.dni.nullable is False
    assert Paciente.telefono.nullable is False
    assert Paciente.nombre.nullable is False
    assert Paciente.apellido.nullable is False


def test_usuario_and_roles_model_attributes():
    assert Usuario.__tablename__ == "usuario"
    assert Rol.__tablename__ == "rol"
    assert UsuarioRol.__tablename__ == "usuario_rol"

    assert Usuario.email.nullable is False
    assert Usuario.hashed_password.nullable is False

    # Foreign keys in UsuarioRol must be indexed
    assert UsuarioRol.usuario_id.index is True
    assert UsuarioRol.rol_id.index is True


def test_disponibilidad_model_attributes():
    assert Disponibilidad.__tablename__ == "disponibilidad"
    assert Disponibilidad.profesional_id.index is True
    assert Disponibilidad.dia_semana.nullable is False
    assert Disponibilidad.hora_inicio.nullable is False
    assert Disponibilidad.hora_fin.nullable is False


def test_obra_social_and_nomenclador_attributes():
    assert ObraSocial.__tablename__ == "obra_social"
    assert Nomenclador.__tablename__ == "nomenclador"

    assert Nomenclador.obra_social_id.index is True
    assert Nomenclador.tratamiento_id.index is True
    # Verify Numeric type for money/percentages (R4)
    assert isinstance(Nomenclador.cobertura_porcentaje.type, Numeric)
    assert isinstance(Nomenclador.arancel_diferencial.type, Numeric)


def test_registro_auditoria_attributes():
    assert RegistroAuditoria.__tablename__ == "registro_auditoria"
    assert RegistroAuditoria.usuario_id.index is True
    assert RegistroAuditoria.created_at.index is True


def test_turno_has_indexed_paciente_fk():
    assert hasattr(Turno, "paciente_id")
    assert Turno.paciente_id.index is True
