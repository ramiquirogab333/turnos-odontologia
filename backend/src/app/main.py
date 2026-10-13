"""FastAPI application entrypoint (R13/R15/R16/R17)."""

from fastapi import FastAPI
from sqlalchemy import select

from app.shared.db import get_session_factory
from app.shared.exceptions import OverlapError, ReferenceNotFoundError
from app.shared.logger import get_logger
from app.turnos.router import (
    referencia_handler,
    router as turnos_router,
    solape_handler,
)
from app.turnos.schemas import HealthRead

logger = get_logger(__name__)

app = FastAPI(title="Turnos Odontología — C-01", version="0.1.0")
app.include_router(turnos_router)
app.add_exception_handler(OverlapError, solape_handler)  # type: ignore[arg-type]
app.add_exception_handler(ReferenceNotFoundError, referencia_handler)  # type: ignore[arg-type]


@app.get(
    "/api/health",
    response_model=HealthRead,
    summary="Salud mínima: API + PostgreSQL operativos",
    responses={200: {"description": "API y PostgreSQL operativos"}},
)
async def health() -> HealthRead:
    """Return 200 when the API and the PostgreSQL connection are up."""
    async with get_session_factory()() as session:
        await session.execute(select(1))
    logger.info("health ok")
    return HealthRead(status="ok", db="ok")
