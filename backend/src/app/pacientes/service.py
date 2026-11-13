"""Servicio de pacientes: alta, búsqueda por DNI, edición y vínculo con turnos (C-11; O1, O3). I/O async (R16)."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import ObraSocial, Paciente
from app.pacientes.auditoria import auditar
from app.pacientes.errores import DniDuplicadoError, ObraSocialInactivaError, PacienteInexistenteError
from app.pacientes.schemas import PacienteCreate, PacienteOut, PacienteVistaClinicaOut, VinculoTurnoOut
from app.pagos.errores import TurnoInexistenteError
from app.panel.schemas import Ref
from app.plataforma.auditoria import registrar
from app.turnos.models import Turno

SQLSTATE_UNICO = "23505"
CAMPOS_EDITABLES = ("nombre", "apellido", "dni", "telefono", "email", "obra_social_id", "numero_afiliado")


async def _exigir_obra_social_activa(session: AsyncSession, obra_social_id: int | None) -> None:
    if obra_social_id is None:
        return
    activa = (await session.execute(
        select(ObraSocial.id).where(ObraSocial.id == obra_social_id, ObraSocial.is_active.is_(True)))
    ).scalar_one_or_none()
    if activa is None:
        raise ObraSocialInactivaError()


async def _dni_en_uso(session: AsyncSession, dni: str, excepto_id: int | None = None) -> bool:
    consulta = select(Paciente.id).where(Paciente.dni == dni)
    if excepto_id is not None:
        consulta = consulta.where(Paciente.id != excepto_id)
    return (await session.execute(consulta)).first() is not None


async def _cargar_obra_social(session: AsyncSession, obra_social_id: int | None) -> Ref | None:
    if obra_social_id is None:
        return None
    nombre = (await session.execute(select(ObraSocial.nombre).where(ObraSocial.id == obra_social_id))).scalar_one()
    return Ref(id=obra_social_id, nombre=nombre)


async def paciente_out(session: AsyncSession, p: Paciente) -> PacienteOut:
    return PacienteOut(id=int(p.id), nombre=p.nombre, apellido=p.apellido, dni=p.dni, telefono=p.telefono,
                       email=p.email, obra_social=await _cargar_obra_social(session, p.obra_social_id),
                       numero_afiliado=p.numero_afiliado)


async def paciente_vista_clinica(session: AsyncSession, p: Paciente) -> PacienteVistaClinicaOut:
    return PacienteVistaClinicaOut(id=int(p.id), nombre=p.nombre, apellido=p.apellido, dni=p.dni,
                                   obra_social=await _cargar_obra_social(session, p.obra_social_id),
                                   numero_afiliado=p.numero_afiliado)


async def obtener_paciente(session: AsyncSession, paciente_id: int) -> Paciente:
    paciente = await session.get(Paciente, paciente_id)
    if paciente is None:
        raise PacienteInexistenteError()
    return paciente


async def crear_paciente(session: AsyncSession, data: PacienteCreate, usuario_id: int) -> PacienteOut:
    """Alta auditada sin datos personales. Raises: ``DniDuplicadoError``, ``ObraSocialInactivaError``."""
    await _exigir_obra_social_activa(session, data.obra_social_id)
    if await _dni_en_uso(session, data.dni):
        raise DniDuplicadoError()
    paciente = Paciente(**data.model_dump())
    session.add(paciente)
    try:
        await session.flush()
        auditar(session, usuario_id, "alta_paciente", "paciente", paciente.id, {"paciente_id": paciente.id})
        await session.commit()
    except IntegrityError as exc:  # carrera entre dos altas con el mismo DNI: la base decide
        await session.rollback()
        if getattr(getattr(exc, "orig", None), "sqlstate", "") == SQLSTATE_UNICO:
            raise DniDuplicadoError() from exc
        raise
    return await paciente_out(session, paciente)


async def buscar_por_dni(session: AsyncSession, dni: str, usuario_id: int) -> list[PacienteOut]:
    """Búsqueda exacta; la auditoría guarda el id hallado y la cantidad, nunca el DNI buscado (C-13, D8)."""
    filas = (await session.execute(select(Paciente).where(Paciente.dni == dni))).scalars().all()
    resultado = [await paciente_out(session, p) for p in filas]
    registrar(session, accion="busqueda_paciente_dni", entidad="paciente", usuario_id=usuario_id,
              entidad_id=filas[0].id if filas else None, despues={"encontrados": len(filas)})
    await session.commit()
    return resultado


async def auditar_lectura_paciente(session: AsyncSession, paciente_id: int, usuario_id: int) -> None:
    """Registra y confirma la lectura de los datos de un paciente antes de entregarlos (C-13, D8)."""
    registrar(session, accion="lectura_paciente", entidad="paciente", entidad_id=paciente_id, usuario_id=usuario_id)
    await session.commit()


async def editar_paciente(session: AsyncSession, paciente_id: int, data: PacienteCreate,
                          usuario_id: int) -> PacienteOut:
    """Reemplazo de datos administrativos; la auditoría guarda solo los nombres de los campos cambiados."""
    paciente = await obtener_paciente(session, paciente_id)
    await _exigir_obra_social_activa(session, data.obra_social_id)
    if await _dni_en_uso(session, data.dni, excepto_id=paciente_id):
        raise DniDuplicadoError()
    nuevos = data.model_dump()
    cambiados = [c for c in CAMPOS_EDITABLES if getattr(paciente, c) != nuevos[c]]
    for campo in cambiados:
        setattr(paciente, campo, nuevos[campo])
    try:
        await session.flush()
        auditar(session, usuario_id, "edicion_paciente", "paciente", paciente_id, {"campos": cambiados})
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if getattr(getattr(exc, "orig", None), "sqlstate", "") == SQLSTATE_UNICO:
            raise DniDuplicadoError() from exc
        raise
    return await paciente_out(session, paciente)


async def vincular_turno(session: AsyncSession, turno_id: int, paciente_id: int, usuario_id: int) -> VinculoTurnoOut:
    """Asocia (o reemplaza) el paciente de un turno sin tocar estado, horario, seña ni contacto (O1)."""
    turno = (await session.execute(
        select(Turno).where(Turno.id == turno_id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if turno is None:
        await session.rollback()
        raise TurnoInexistenteError()
    await obtener_paciente(session, paciente_id)
    anterior = turno.paciente_id
    turno.paciente_id = paciente_id
    auditar(session, usuario_id, "vinculo_turno_paciente", "turno", turno_id,
            {"paciente_anterior_id": anterior, "paciente_nuevo_id": paciente_id})
    await session.commit()
    return VinculoTurnoOut(turno_id=turno_id, paciente_id=paciente_id)
