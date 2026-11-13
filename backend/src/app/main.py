"""FastAPI application entrypoint (R13/R15/R16/R17)."""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy import select

from app.shared.db import get_session_factory
from app.shared.exceptions import OverlapError, ReferenceNotFoundError
from app.shared.limites import registrar_handlers_limites
from app.shared.logger import get_logger
from app.shared.red import instalar_proxy_headers
from app.shared.settings import get_settings
from app.turnos.router import (
    referencia_handler,
    router as turnos_router,
    solape_handler,
)
from app.turnos.schemas import HealthRead

from app.auth.router import router as auth_router
from app.catalogo.router import (
    router_disponibilidad,
    router_profesionales,
    router_sillones,
    router_tratamientos,
)
from app.caja.http import registrar_handlers as registrar_handlers_caja
from app.caja.router import router as caja_router
from app.integraciones.gcal.router import router as gcal_router
from app.notificaciones.router import router as recordatorios_router
from app.pagos.barrido import ciclo_barrido
from app.gestion.router import router as gestion_router
from app.pagos.router_admin import router as sena_admin_router
from app.pagos.router_public import router as sena_public_router
from app.pagos.router_webhook import router as sena_webhook_router
from app.clinica.router import router as clinica_router
from app.pacientes.http import registrar_handlers as registrar_handlers_clinicos
from app.pacientes.router import router as pacientes_router
from app.panel.router import router as panel_router
from app.panel.router_indicadores import router as indicadores_router
from app.public.router import router as public_router

logger = get_logger(__name__)



@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Barrido de pre-reservas vencidas dentro de la API solo si ``SENA_BARRIDO_EN_API`` (C-09, O11).

    Por defecto lo corre el worker (``app.jobs``); la bandera sirve para desarrollo y pruebas sin Redis.
    """
    settings = get_settings()
    # Pool de Redis para los límites de solicitudes (C-15); no conecta hasta el primer uso y falla abierto (O5).
    application.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
    application.state.barrido_task = None
    if settings.sena_barrido_habilitado and settings.sena_barrido_en_api:
        application.state.barrido_task = asyncio.create_task(
            ciclo_barrido(get_session_factory(), settings.sena_barrido_segundos))
    try:
        yield
    finally:
        await application.state.redis.aclose()
        tarea = application.state.barrido_task
        if tarea is not None:
            tarea.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await tarea


app = FastAPI(title="Turnos Odontología — C-01", version="0.1.0", lifespan=lifespan)
instalar_proxy_headers(app, get_settings().trusted_proxies)  # C-15 D6: vacío = IP del socket
app.include_router(turnos_router)
app.include_router(auth_router)
app.include_router(router_tratamientos)
app.include_router(router_profesionales)
app.include_router(router_sillones)
app.include_router(router_disponibilidad)
app.include_router(public_router)
app.include_router(sena_public_router)
app.include_router(sena_webhook_router)
app.include_router(sena_admin_router)
app.include_router(gestion_router)
app.include_router(panel_router)
app.include_router(pacientes_router)
app.include_router(clinica_router)
app.include_router(caja_router)
app.include_router(indicadores_router)
app.include_router(recordatorios_router)
app.include_router(gcal_router)
registrar_handlers_limites(app)
registrar_handlers_clinicos(app)
registrar_handlers_caja(app)
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
