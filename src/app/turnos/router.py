"""HTTP router for the internal turno primitive (D9).

``POST /api/turnos`` is an **identity-free internal primitive**: it receives
no patient identity (no Paciente/nombre/teléfono). Change C-05 reuses this
endpoint from ``POST /api/public/turnos`` (which adds nombre+teléfono and a
management code) — reuse, not supersede: this primitive stays for the manual
use of C-08.

Responses: 201 created (``fin`` derived), 409 overlap with enum motivo
(``profesional`` wins when both collide), 422 validation/unknown FK/past
``inicio``. An exclusion-violation (SQLSTATE 23P01) is always mapped to 409,
never 500.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.db import get_session
from app.shared.exceptions import OverlapError, ReferenceNotFoundError
from app.turnos import service
from app.turnos.schemas import ConflictoSolape, TurnoCreate, TurnoRead

router = APIRouter(prefix="/api/turnos", tags=["turnos"])

MAX_INTENTOS_CARRERA = 3


async def solape_handler(request: object, exc: OverlapError) -> JSONResponse:
    """Map an exclusion/pre-check overlap to 409 with enum motivo (never 500)."""
    return JSONResponse(
        status_code=409,
        content={"detail": f"Solape por {exc.motivo}", "motivo": exc.motivo},
    )


async def referencia_handler(request: object, exc: ReferenceNotFoundError) -> JSONResponse:
    """Map an unknown FK parent to 422."""
    return JSONResponse(
        status_code=422, content={"detail": f"Referencia inexistente: {exc.campo}"}
    )


@router.post(
    "",
    response_model=TurnoRead,
    status_code=201,
    summary="Crear turno (primitiva interna identity-free, reused by C-05)",
    responses={
        201: {"description": "Turno creado con `fin` derivado del tratamiento"},
        409: {"model": ConflictoSolape, "description": "Solape por profesional o sillón"},
        422: {"description": "`fin` enviado, `inicio` pasado, FK inexistente o campo faltante"},
    },
)
async def crear_turno(
    data: TurnoCreate, session: AsyncSession = Depends(get_session)
) -> TurnoRead:
    """Create a turno blocking its slot on profesional AND sillon (D9)."""
    for intento in range(MAX_INTENTOS_CARRERA):
        try:
            turno = await service.create_turno(session, data)
            await session.commit()
            break
        except DBAPIError as exc:
            # Carrera simétrica: los INSERTs concurrentes pueden deadlockear
            # (40P01) en vez de violar el EXCLUDE. Rollback + reintento: el
            # ganador ya confirmó y el pre-check devuelve el 409 correcto.
            await session.rollback()
            if getattr(getattr(exc, "orig", None), "sqlstate", "") == "40P01" and intento < MAX_INTENTOS_CARRERA - 1:
                continue
            raise
        except (OverlapError, ReferenceNotFoundError):
            await session.rollback()
            raise
    return TurnoRead.model_validate(turno)
