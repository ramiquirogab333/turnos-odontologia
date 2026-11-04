"""Routers admin del catálogo protegidos con RBAC (C-03).

Endpoints bajo prefijo ``/api/admin/``:
- ``GET/POST/PUT/DELETE /api/admin/tratamientos``
- ``GET/POST/PUT/DELETE /api/admin/profesionales``
- ``GET/POST/PUT/DELETE /api/admin/sillones``
- ``GET/POST/PUT/DELETE /api/admin/disponibilidad``

Cada endpoint exige rol ``recepcion`` u ``admin`` (RBAC de C-03); cualquier otro
rol recibe 403. Las escrituras auditan en ``RegistroAuditoria`` dentro de la
misma transacción (RN-GL-01).
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import PermissionContext, get_current_user
from app.catalogo.schemas import (
    DisponibilidadCreate,
    DisponibilidadRead,
    DisponibilidadUpdate,
    ProfesionalCreate,
    ProfesionalRead,
    ProfesionalUpdate,
    SillonCreate,
    SillonRead,
    SillonUpdate,
    TratamientoCreate,
    TratamientoRead,
    TratamientoUpdate,
)
from app.catalogo.service import (
    DisponibilidadService,
    ProfesionalService,
    SillonService,
    TratamientoService,
)
from app.shared.db import get_session

router_tratamientos = APIRouter(prefix="/api/admin/tratamientos", tags=["admin-tratamientos"])
router_profesionales = APIRouter(prefix="/api/admin/profesionales", tags=["admin-profesionales"])
router_sillones = APIRouter(prefix="/api/admin/sillones", tags=["admin-sillones"])
router_disponibilidad = APIRouter(prefix="/api/admin/disponibilidad", tags=["admin-disponibilidad"])


async def require_recepcion_o_admin(context: PermissionContext = Depends(get_current_user)):
    """Exige rol recepcion u admin; cualquier otro rol -> 403."""
    if not (context.tiene_rol("recepcion") or context.tiene_rol("admin")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Rol requerido: recepcion o admin",
        )
    return context


def _ip(request: Request) -> str:
    return request.client.host if request.client else "testclient"


# ===========================================================================
# Tratamientos
# ===========================================================================

@router_tratamientos.get("", response_model=list[TratamientoRead])
async def listar_tratamientos(
    session: AsyncSession = Depends(get_session),
    context: PermissionContext = Depends(require_recepcion_o_admin),
) -> list[TratamientoRead]:
    items = await TratamientoService(session).list_all()
    return [TratamientoRead.model_validate(i) for i in items]


@router_tratamientos.get("/{id_}", response_model=TratamientoRead)
async def obtener_tratamiento(
    id_: int,
    session: AsyncSession = Depends(get_session),
    context: PermissionContext = Depends(require_recepcion_o_admin),
) -> TratamientoRead:
    servicio = TratamientoService(session)
    entity = await servicio.get_by_id(id_)
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tratamiento no encontrado")
    return TratamientoRead.model_validate(entity)


@router_tratamientos.post("", response_model=TratamientoRead, status_code=201)
async def crear_tratamiento(
    data: TratamientoCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    context: PermissionContext = Depends(require_recepcion_o_admin),
) -> TratamientoRead:
    servicio = TratamientoService(session)
    entity = await servicio.create(data, usuario_id=context.usuario_id, ip=_ip(request))
    await session.commit()
    return TratamientoRead.model_validate(entity)


@router_tratamientos.put("/{id_}", response_model=TratamientoRead)
async def actualizar_tratamiento(
    id_: int,
    data: TratamientoUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    context: PermissionContext = Depends(require_recepcion_o_admin),
) -> TratamientoRead:
    servicio = TratamientoService(session)
    entity = await servicio.update(id_, data, usuario_id=context.usuario_id, ip=_ip(request))
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tratamiento no encontrado")
    await session.commit()
    return TratamientoRead.model_validate(entity)


@router_tratamientos.delete("/{id_}", status_code=204)
async def eliminar_tratamiento(
    id_: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    context: PermissionContext = Depends(require_recepcion_o_admin),
) -> None:
    servicio = TratamientoService(session)
    ok = await servicio.delete(id_, usuario_id=context.usuario_id, ip=_ip(request))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tratamiento no encontrado")
    await session.commit()


# ===========================================================================
# Profesionales
# ===========================================================================

@router_profesionales.get("", response_model=list[ProfesionalRead])
async def listar_profesionales(
    session: AsyncSession = Depends(get_session),
    context: PermissionContext = Depends(require_recepcion_o_admin),
) -> list[ProfesionalRead]:
    items = await ProfesionalService(session).list_all()
    return [ProfesionalRead.model_validate(i) for i in items]


@router_profesionales.get("/{id_}", response_model=ProfesionalRead)
async def obtener_profesional(
    id_: int,
    session: AsyncSession = Depends(get_session),
    context: PermissionContext = Depends(require_recepcion_o_admin),
) -> ProfesionalRead:
    servicio = ProfesionalService(session)
    entity = await servicio.get_by_id(id_)
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profesional no encontrado")
    return ProfesionalRead.model_validate(entity)


@router_profesionales.post("", response_model=ProfesionalRead, status_code=201)
async def crear_profesional(
    data: ProfesionalCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    context: PermissionContext = Depends(require_recepcion_o_admin),
) -> ProfesionalRead:
    servicio = ProfesionalService(session)
    entity = await servicio.create(data, usuario_id=context.usuario_id, ip=_ip(request))
    await session.commit()
    return ProfesionalRead.model_validate(entity)


@router_profesionales.put("/{id_}", response_model=ProfesionalRead)
async def actualizar_profesional(
    id_: int,
    data: ProfesionalUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    context: PermissionContext = Depends(require_recepcion_o_admin),
) -> ProfesionalRead:
    servicio = ProfesionalService(session)
    entity = await servicio.update(id_, data, usuario_id=context.usuario_id, ip=_ip(request))
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profesional no encontrado")
    await session.commit()
    return ProfesionalRead.model_validate(entity)


@router_profesionales.delete("/{id_}", status_code=204)
async def eliminar_profesional(
    id_: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    context: PermissionContext = Depends(require_recepcion_o_admin),
) -> None:
    servicio = ProfesionalService(session)
    ok = await servicio.delete(id_, usuario_id=context.usuario_id, ip=_ip(request))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profesional no encontrado")
    await session.commit()


# ===========================================================================
# Sillones
# ===========================================================================

@router_sillones.get("", response_model=list[SillonRead])
async def listar_sillones(
    session: AsyncSession = Depends(get_session),
    context: PermissionContext = Depends(require_recepcion_o_admin),
) -> list[SillonRead]:
    items = await SillonService(session).list_all()
    return [SillonRead.model_validate(i) for i in items]


@router_sillones.get("/{id_}", response_model=SillonRead)
async def obtener_sillon(
    id_: int,
    session: AsyncSession = Depends(get_session),
    context: PermissionContext = Depends(require_recepcion_o_admin),
) -> SillonRead:
    servicio = SillonService(session)
    entity = await servicio.get_by_id(id_)
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sillon no encontrado")
    return SillonRead.model_validate(entity)


@router_sillones.post("", response_model=SillonRead, status_code=201)
async def crear_sillon(
    data: SillonCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    context: PermissionContext = Depends(require_recepcion_o_admin),
) -> SillonRead:
    servicio = SillonService(session)
    entity = await servicio.create(data, usuario_id=context.usuario_id, ip=_ip(request))
    await session.commit()
    return SillonRead.model_validate(entity)


@router_sillones.put("/{id_}", response_model=SillonRead)
async def actualizar_sillon(
    id_: int,
    data: SillonUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    context: PermissionContext = Depends(require_recepcion_o_admin),
) -> SillonRead:
    servicio = SillonService(session)
    entity = await servicio.update(id_, data, usuario_id=context.usuario_id, ip=_ip(request))
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sillon no encontrado")
    await session.commit()
    return SillonRead.model_validate(entity)


@router_sillones.delete("/{id_}", status_code=204)
async def eliminar_sillon(
    id_: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    context: PermissionContext = Depends(require_recepcion_o_admin),
) -> None:
    servicio = SillonService(session)
    ok = await servicio.delete(id_, usuario_id=context.usuario_id, ip=_ip(request))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sillon no encontrado")
    await session.commit()


# ===========================================================================
# Disponibilidad
# ===========================================================================

@router_disponibilidad.get("", response_model=list[DisponibilidadRead])
async def listar_disponibilidad(
    session: AsyncSession = Depends(get_session),
    context: PermissionContext = Depends(require_recepcion_o_admin),
) -> list[DisponibilidadRead]:
    items = await DisponibilidadService(session).list_all()
    return [DisponibilidadRead.model_validate(i) for i in items]


@router_disponibilidad.get("/{id_}", response_model=DisponibilidadRead)
async def obtener_disponibilidad(
    id_: int,
    session: AsyncSession = Depends(get_session),
    context: PermissionContext = Depends(require_recepcion_o_admin),
) -> DisponibilidadRead:
    servicio = DisponibilidadService(session)
    entity = await servicio.get_by_id(id_)
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Disponibilidad no encontrada")
    return DisponibilidadRead.model_validate(entity)


@router_disponibilidad.post("", response_model=DisponibilidadRead, status_code=201)
async def crear_disponibilidad(
    data: DisponibilidadCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    context: PermissionContext = Depends(require_recepcion_o_admin),
) -> DisponibilidadRead:
    servicio = DisponibilidadService(session)
    entity = await servicio.create(data, usuario_id=context.usuario_id, ip=_ip(request))
    await session.commit()
    return DisponibilidadRead.model_validate(entity)


@router_disponibilidad.put("/{id_}", response_model=DisponibilidadRead)
async def actualizar_disponibilidad(
    id_: int,
    data: DisponibilidadUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    context: PermissionContext = Depends(require_recepcion_o_admin),
) -> DisponibilidadRead:
    servicio = DisponibilidadService(session)
    entity = await servicio.update(id_, data, usuario_id=context.usuario_id, ip=_ip(request))
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Disponibilidad no encontrada")
    await session.commit()
    return DisponibilidadRead.model_validate(entity)


@router_disponibilidad.delete("/{id_}", status_code=204)
async def eliminar_disponibilidad(
    id_: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    context: PermissionContext = Depends(require_recepcion_o_admin),
) -> None:
    servicio = DisponibilidadService(session)
    ok = await servicio.delete(id_, usuario_id=context.usuario_id, ip=_ip(request))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Disponibilidad no encontrada")
    await session.commit()

# Router principal que agrupa todos los sub-routers de catalogo.
router = APIRouter(tags=["admin-catalogo"])
router.include_router(router_tratamientos)
router.include_router(router_profesionales)
router.include_router(router_sillones)
router.include_router(router_disponibilidad)

# Aliases por convención de importación en main.py.
catalogo_router_tratamientos = router_tratamientos
catalogo_router_profesionales = router_profesionales
catalogo_router_sillones = router_sillones
catalogo_router_disponibilidad = router_disponibilidad
