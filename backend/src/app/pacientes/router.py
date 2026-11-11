"""Router de pacientes del panel (C-11, D1): alta, búsqueda por DNI, consulta, edición y vínculo con turnos.

Las escrituras y la búsqueda son de recepción y admin (``require_recepcion_o_admin`` corta antes de mirar el alcance);
la consulta de un paciente la hace también la odontóloga, solo sobre sus pacientes y con el esquema de O3.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import PermissionContext, get_current_user, require_recepcion_o_admin
from app.gestion.deps import get_reloj
from app.pacientes import ficha_service, listado, service
from app.pacientes.alcance import alcance_paciente
from app.pacientes.schemas import (
    FichaOut,
    FichaUpdate,
    PacienteCreate,
    PacienteOut,
    PacienteUpdate,
    PacienteVistaClinicaOut,
    VinculoTurnoOut,
    VinculoTurnoUpdate,
)
from app.pacientes.schemas_listado import ListadoOut, ListadoQuery
from app.panel.schemas import ErrorPanelBody
from app.shared.db import get_session

router = APIRouter(prefix="/api/panel", tags=["pacientes"])

_ERRORES = {
    401: {"description": "Sin token de acceso válido"},
    403: {"model": ErrorPanelBody, "description": "Sin permisos o paciente ajeno (`paciente_ajeno`)"},
    404: {"model": ErrorPanelBody, "description": "Paciente o turno inexistente"},
}


@router.post("/pacientes", response_model=PacienteOut, status_code=status.HTTP_201_CREATED,
             summary="Alta de paciente (recepción/admin); DNI único", responses={
                 **_ERRORES, 409: {"model": ErrorPanelBody, "description": "`dni_duplicado`"},
                 422: {"description": "Datos inválidos u `obra_social_inactiva`"}})
async def alta_paciente(
    data: PacienteCreate,
    contexto: PermissionContext = Depends(require_recepcion_o_admin),
    session: AsyncSession = Depends(get_session),
) -> PacienteOut:
    return await service.crear_paciente(session, data, contexto.usuario_id)


@router.get("/pacientes", response_model=list[PacienteOut],
            summary="Búsqueda exacta por DNI (cero o un resultado), solo recepción/admin", responses=_ERRORES)
async def buscar_paciente(
    dni: Annotated[str, Query(pattern=r"^[0-9]{7,8}$")],
    contexto: PermissionContext = Depends(require_recepcion_o_admin),
    session: AsyncSession = Depends(get_session),
) -> list[PacienteOut]:
    return await service.buscar_por_dni(session, dni)


# Declarado ANTES de ``/pacientes/{paciente_id}``: si no, "listado" se interpretaría como un id.
@router.get("/pacientes/listado", response_model=ListadoOut,
            summary="Listado paginado con búsqueda libre (nombre, apellido o comienzo del DNI) y ausencias por paciente",
            responses={401: _ERRORES[401], 403: _ERRORES[403], 422: {"description": "`q` de 2 a 60 caracteres, `orden` o paginación inválidos"}})
async def listar_pacientes(
    query: Annotated[ListadoQuery, Query()],
    contexto: PermissionContext = Depends(require_recepcion_o_admin),
    session: AsyncSession = Depends(get_session),
) -> ListadoOut:
    return await listado.listar_pacientes(session, query)


@router.get("/pacientes/{paciente_id}", response_model=PacienteOut | PacienteVistaClinicaOut,
            summary="Datos del paciente: completos para recepción/admin; sin teléfono ni email para la odontóloga",
            responses=_ERRORES)
async def consultar_paciente(
    paciente_id: int,
    contexto: PermissionContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    ahora: datetime = Depends(get_reloj),
) -> PacienteOut | PacienteVistaClinicaOut:
    alcance = await alcance_paciente(session, contexto, paciente_id, ahora)
    paciente = await service.obtener_paciente(session, paciente_id)
    if alcance.ve_contacto:
        return await service.paciente_out(session, paciente)
    return await service.paciente_vista_clinica(session, paciente)


@router.put("/pacientes/{paciente_id}", response_model=PacienteOut,
            summary="Edición de datos administrativos (recepción/admin)", responses={
                **_ERRORES, 409: {"model": ErrorPanelBody, "description": "`dni_duplicado`"},
                422: {"description": "Datos inválidos u `obra_social_inactiva`"}})
async def editar_paciente(
    paciente_id: int,
    data: PacienteUpdate,
    contexto: PermissionContext = Depends(require_recepcion_o_admin),
    session: AsyncSession = Depends(get_session),
) -> PacienteOut:
    return await service.editar_paciente(session, paciente_id, data, contexto.usuario_id)


@router.put("/turnos/{turno_id}/paciente", response_model=VinculoTurnoOut,
            summary="Vincula (o corrige el vínculo de) un turno con un paciente (recepción/admin)",
            responses=_ERRORES)
async def vincular_turno(
    turno_id: int,
    data: VinculoTurnoUpdate,
    contexto: PermissionContext = Depends(require_recepcion_o_admin),
    session: AsyncSession = Depends(get_session),
) -> VinculoTurnoOut:
    return await service.vincular_turno(session, turno_id, data.paciente_id, contexto.usuario_id)


@router.get("/pacientes/{paciente_id}/ficha", response_model=FichaOut,
            summary="Ficha clínica: antecedentes, versión e historia de turnos (sin datos de contacto)",
            responses=_ERRORES)
async def consultar_ficha(
    paciente_id: int,
    contexto: PermissionContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    ahora: datetime = Depends(get_reloj),
) -> FichaOut:
    return await ficha_service.consultar_ficha(session, contexto, paciente_id, ahora)


@router.put("/pacientes/{paciente_id}/ficha", response_model=FichaOut,
            summary="Reemplaza los antecedentes con control de versión (recepción/admin y odontóloga con acceso completo)",
            responses={**_ERRORES, 409: {"model": ErrorPanelBody, "description": "`version_desactualizada`"},
                       422: {"description": "Texto de más de 2000 caracteres o cuerpo inválido"}})
async def editar_ficha(
    paciente_id: int,
    data: FichaUpdate,
    contexto: PermissionContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    ahora: datetime = Depends(get_reloj),
) -> FichaOut:
    return await ficha_service.editar_ficha(session, contexto, paciente_id, data, ahora)
