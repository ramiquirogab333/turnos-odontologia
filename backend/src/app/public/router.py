"""Router público: disponibilidad y reserva sin autenticación (C-05).

Endpoints bajo prefijo ``/api/public/``:
- GET  /api/public/disponibilidad: franjas horarias libres (sin auth).
- POST /api/public/turnos: reserva pública con nombre + teléfono E.164.

R15: esquemas Pydantic de entrada/salida en el borde.
R16: I/O asíncrono, nunca bloquea el event loop.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.public.schemas import (
    DisponibilidadPublicaQuery,
    DisponibilidadPublicaResponse,
    DisponibilidadPublicaSlot,
    ReservaConflictoBody,
    ReservaPublicaRequest,
    ReservaPublicaResponse,
    ProfesionalPublico,
    TratamientoPublico,
)
from app.public.service import (
    FueraDeDisponibilidadError,
    ReservaConflictoError,
    consultar_disponibilidad,
    reservar_turno_publico,
)
from app.models.core import Disponibilidad
from app.shared.db import get_session
from app.turnos.models import Profesional, Tratamiento

router = APIRouter(prefix="/api/public", tags=["public"])


@router.get(
    "/tratamientos",
    response_model=list[TratamientoPublico],
    summary="Tratamientos reservables (paso 1 del wizard)",
)
async def tratamientos_publicos(session: AsyncSession = Depends(get_session)) -> list[TratamientoPublico]:
    """Lista de solo lectura, ordenada por nombre."""
    filas = await session.execute(select(Tratamiento).order_by(Tratamiento.nombre, Tratamiento.id))
    return [TratamientoPublico.model_validate(t) for t in filas.scalars().all()]


@router.get(
    "/profesionales",
    response_model=list[ProfesionalPublico],
    summary="Profesionales con agenda vigente",
)
async def profesionales_publicos(session: AsyncSession = Depends(get_session)) -> list[ProfesionalPublico]:
    """Solo profesionales con al menos una franja activa (RN-TU-07); sin matrícula."""
    vigente = select(Disponibilidad.profesional_id).where(Disponibilidad.is_active.is_(True))
    filas = await session.execute(
        select(Profesional).where(Profesional.id.in_(vigente)).order_by(Profesional.nombre, Profesional.id)
    )
    return [ProfesionalPublico.model_validate(p) for p in filas.scalars().all()]


@router.get(
    "/disponibilidad",
    response_model=DisponibilidadPublicaResponse,
    summary="Franjas horarias libres para un profesional y tratamiento",
    responses={200: {"description": "Lista de slots libres"}},
)
async def disponibilidad(
    query: Annotated[DisponibilidadPublicaQuery, Query()],
    session: AsyncSession = Depends(get_session),
) -> DisponibilidadPublicaResponse:
    """Devuelve slots libres donde profesional y al menos un sillón están disponibles."""
    slots = await consultar_disponibilidad(
        session,
        profesional_id=query.profesional_id,
        tratamiento_id=query.tratamiento_id,
        desde=query.desde,
        hasta=query.hasta,
    )
    return DisponibilidadPublicaResponse(
        slots=[
            DisponibilidadPublicaSlot(
                inicio=s["inicio"],
                fin=s["fin"],
                profesional_id=s["profesional_id"],
                sillon_id=s["sillon_id"],
            )
            for s in slots
        ]
    )


@router.post(
    "/turnos",
    response_model=ReservaPublicaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Reserva pública de turno sin autenticación",
    responses={
        201: {"description": "Turno reservado con código de gestión"},
        409: {"model": ReservaConflictoBody, "description": "Solape de agenda con alternativas libres"},
        422: {"description": "Validación de teléfono/FK/inicio/campos extra"},
    },
)
async def reservar_turno(
    data: ReservaPublicaRequest,
    session: AsyncSession = Depends(get_session),
) -> ReservaPublicaResponse:
    """Crea un turno público asignando sillón disponible de forma atómica."""
    try:
        resultado = await reservar_turno_publico(session, data)
    except FueraDeDisponibilidadError as exc:
        return JSONResponse(status_code=422, content={"detail": str(exc)})
    except ReservaConflictoError as exc:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=ReservaConflictoBody(
                detail=f"Solape por {exc.motivo}",
                motivo=exc.motivo,
                alternativas=exc.alternativas,
            ).model_dump(),
        )
    return ReservaPublicaResponse(**resultado)
