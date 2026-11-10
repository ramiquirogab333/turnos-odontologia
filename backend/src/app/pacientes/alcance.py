"""Alcance por paciente (C-11, D2; O2, O3, O4, O16). Decide qué puede ver y escribir cada rol sobre un paciente."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Literal

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import PermissionContext
from app.models.core import Paciente, Usuario
from app.pacientes.errores import PacienteAjenoError, PacienteInexistenteError
from app.panel.service import SinAccesoAlPanelError, SinProfesionalAsociadoError
from app.turnos.models import Turno

# "12 meses" = 365 días exactos sobre instantes UTC (O16): no depende del calendario ni del horario de verano.
# Única fuente del valor: los tests la importan.
VENTANA_ACCESO_CLINICO: Final = timedelta(days=365)

Nivel = Literal["total", "clinico_completo", "clinico_lectura"]


@dataclass(frozen=True)
class AlcancePaciente:
    nivel: Nivel
    escribe_clinica: bool
    escribe_administrativo: bool
    ve_contacto: bool
    ve_pagos: bool


TOTAL: Final = AlcancePaciente("total", True, True, True, True)


async def alcance_paciente(session: AsyncSession, contexto: PermissionContext, paciente_id: int,
                           ahora: datetime) -> AlcancePaciente:
    """Alcance de ``contexto`` sobre el paciente.

    Raises:
        PacienteInexistenteError: el paciente no existe (se evalúa primero, 404).
        SinAccesoAlPanelError: el usuario no tiene ningún rol del panel.
        SinProfesionalAsociadoError: odontóloga sin profesional asociado.
        PacienteAjenoError: ningún turno ``atendido`` con su profesional (O2).
    """
    if (await session.execute(select(Paciente.id).where(Paciente.id == paciente_id))).scalar_one_or_none() is None:
        raise PacienteInexistenteError()
    if contexto.tiene_rol("recepcion") or contexto.tiene_rol("admin"):  # el permiso más amplio gana
        return TOTAL
    if not contexto.tiene_rol("odontologo"):
        raise SinAccesoAlPanelError()
    profesional_id = (await session.execute(
        select(Usuario.profesional_id).where(Usuario.id == contexto.usuario_id))).scalar_one_or_none()
    if profesional_id is None:
        raise SinProfesionalAsociadoError()

    ultimo_atendido, hay_pendiente = (await session.execute(
        select(
            func.max(Turno.inicio).filter(Turno.estado == "atendido"),
            func.coalesce(func.bool_or(and_(Turno.estado.in_(("reservado", "confirmado")), Turno.fin > ahora)), False),
        ).where(Turno.paciente_id == paciente_id, Turno.profesional_id == profesional_id))).one()
    if ultimo_atendido is None:  # el acceso se gana al atender, no al agendar
        raise PacienteAjenoError()
    completo = hay_pendiente or ultimo_atendido >= ahora - VENTANA_ACCESO_CLINICO
    return AlcancePaciente("clinico_completo" if completo else "clinico_lectura", completo, False, False, False)
