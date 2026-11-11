"""Router de indicadores (C-12, D1): ocupación y ausentismo, solo recepción y admin (O15). Sin auditoría de lectura:
son agregados sin datos de personas."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import PermissionContext, require_recepcion_o_admin
from app.caja.schemas import RangoFechas
from app.gestion.deps import get_reloj
from app.panel import indicadores
from app.panel.schemas_indicadores import AusentismoOut, OcupacionOut, OcupacionQuery
from app.shared.db import get_session

router = APIRouter(prefix="/api/panel", tags=["indicadores"])

_ERRORES = {
    401: {"description": "Sin token de acceso válido"},
    403: {"description": "Solo recepción y admin"},
    422: {"description": "Rango inválido o `sillon_id` inexistente"},
}


@router.get("/ocupacion", response_model=OcupacionOut,
            summary="Ocupación por sillón y día de la clínica (hasta 31 días); `en_espera` nunca cuenta (R8)",
            responses=_ERRORES)
async def ocupacion(
    query: Annotated[OcupacionQuery, Query()],
    contexto: PermissionContext = Depends(require_recepcion_o_admin),
    session: AsyncSession = Depends(get_session),
) -> OcupacionOut:
    return await indicadores.consultar_ocupacion(session, query)


@router.get("/ausentismo", response_model=AusentismoOut,
            summary="Ausentismo del período (hasta 366 días), por profesional, con `sin_marcar` y recupero por señas retenidas",
            responses=_ERRORES)
async def ausentismo(
    rango: Annotated[RangoFechas, Query()],
    contexto: PermissionContext = Depends(require_recepcion_o_admin),
    session: AsyncSession = Depends(get_session),
    ahora: datetime = Depends(get_reloj),
) -> AusentismoOut:
    return await indicadores.consultar_ausentismo(session, rango, ahora)
