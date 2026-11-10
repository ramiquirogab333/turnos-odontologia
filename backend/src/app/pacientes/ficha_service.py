"""Servicio de la ficha clínica (C-11, D4; O2, O4, O5, O6, O14, O16). I/O async (R16)."""

from datetime import datetime

from sqlalchemy import and_, not_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import PermissionContext
from app.pacientes.alcance import AlcancePaciente, alcance_paciente
from app.pacientes.auditoria import auditar
from app.pacientes.errores import AccesoClinicoVencidoError, VersionDesactualizadaError
from app.pacientes.models import Ficha
from app.pacientes.schemas import FichaOut, FichaUpdate, TurnoHistoriaOut
from app.panel.schemas import Ref
from app.panel.service import zona_clinica
from app.turnos.models import Profesional, Tratamiento, Turno

CAMPOS_FICHA = ("alergias", "medicacion", "antecedentes_medicos", "observaciones")


def exigir_escritura_clinica(alcance: AlcancePaciente) -> None:
    """Con acceso de solo lectura (O16) toda escritura clínica es 403 ``acceso_clinico_vencido``."""
    if not alcance.escribe_clinica:
        raise AccesoClinicoVencidoError()


async def _historia(session: AsyncSession, paciente_id: int, ahora: datetime) -> list[TurnoHistoriaOut]:
    """Turnos vinculados de todas las profesionales (O14), del más reciente al más antiguo, sin pre-reservas vencidas."""
    zona = zona_clinica()
    filas = (await session.execute(
        select(Turno.id, Turno.inicio, Turno.fin, Turno.estado, Profesional.id, Profesional.nombre,
               Tratamiento.id, Tratamiento.nombre)
        .join(Profesional, Profesional.id == Turno.profesional_id)
        .join(Tratamiento, Tratamiento.id == Turno.tratamiento_id)
        .where(Turno.paciente_id == paciente_id,
               not_(and_(Turno.estado == "en_espera", Turno.en_espera_vence_en <= ahora)))
        .order_by(Turno.inicio.desc(), Turno.id.desc()))).all()
    return [TurnoHistoriaOut(turno_id=int(t), inicio=i.astimezone(zona), fin=f.astimezone(zona), estado=e,
                             profesional=Ref(id=int(pid), nombre=pn), tratamiento=Ref(id=int(tid), nombre=tn))
            for t, i, f, e, pid, pn, tid, tn in filas]


def _ficha_out(paciente_id: int, ficha: Ficha | None, historia: list[TurnoHistoriaOut]) -> FichaOut:
    if ficha is None:
        return FichaOut(paciente_id=paciente_id, alergias="", medicacion="", antecedentes_medicos="",
                        observaciones="", version=0, actualizado_por=None, historia=historia)
    return FichaOut(paciente_id=paciente_id, alergias=ficha.alergias, medicacion=ficha.medicacion,
                    antecedentes_medicos=ficha.antecedentes_medicos, observaciones=ficha.observaciones,
                    version=ficha.version, actualizado_por=ficha.actualizado_por, historia=historia)


async def consultar_ficha(session: AsyncSession, contexto: PermissionContext, paciente_id: int,
                          ahora: datetime) -> FichaOut:
    """Raises: ``PacienteInexistenteError``, ``PacienteAjenoError`` (sin auditoría en ambos casos)."""
    await alcance_paciente(session, contexto, paciente_id, ahora)
    ficha = (await session.execute(select(Ficha).where(Ficha.paciente_id == paciente_id))).scalar_one_or_none()
    salida = _ficha_out(paciente_id, ficha, await _historia(session, paciente_id, ahora))
    auditar(session, contexto.usuario_id, "lectura_ficha", "ficha", paciente_id)
    await session.commit()
    return salida


async def editar_ficha(session: AsyncSession, contexto: PermissionContext, paciente_id: int, data: FichaUpdate,
                       ahora: datetime) -> FichaOut:
    """Reemplaza los antecedentes con control de versión optimista (O6).

    Raises: ``PacienteInexistenteError``, ``PacienteAjenoError``, ``AccesoClinicoVencidoError``,
    ``VersionDesactualizadaError``.
    """
    exigir_escritura_clinica(await alcance_paciente(session, contexto, paciente_id, ahora))
    nuevos = {c: getattr(data, c) for c in CAMPOS_FICHA}
    actual = (await session.execute(select(Ficha).where(Ficha.paciente_id == paciente_id))).scalar_one_or_none()
    if data.version == 0:
        if actual is not None:  # la ficha ya existe: la versión 0 quedó vieja
            raise VersionDesactualizadaError()
        creada = (await session.execute(
            pg_insert(Ficha).values(paciente_id=paciente_id, actualizado_por=contexto.usuario_id, version=1, **nuevos)
            .on_conflict_do_nothing(index_elements=["paciente_id"]).returning(Ficha.id))).scalar_one_or_none()
        if creada is None:  # otra edición ganó la carrera
            await session.rollback()
            raise VersionDesactualizadaError()
        cambiados = [c for c in CAMPOS_FICHA if nuevos[c]]
    else:
        if actual is None or actual.version != data.version:
            raise VersionDesactualizadaError()
        cambiados = [c for c in CAMPOS_FICHA if getattr(actual, c) != nuevos[c]]
        filas = (await session.execute(
            update(Ficha).where(Ficha.paciente_id == paciente_id, Ficha.version == data.version)
            .values(version=Ficha.version + 1, actualizado_por=contexto.usuario_id, **nuevos)
            .returning(Ficha.id))).scalar_one_or_none()
        if filas is None:
            await session.rollback()
            raise VersionDesactualizadaError()
    auditar(session, contexto.usuario_id, "edicion_ficha", "ficha", paciente_id,
            {"campos": cambiados, "version": data.version + 1})
    await session.commit()
    ficha = (await session.execute(
        select(Ficha).where(Ficha.paciente_id == paciente_id).execution_options(populate_existing=True)
    )).scalar_one()
    return _ficha_out(paciente_id, ficha, await _historia(session, paciente_id, ahora))
