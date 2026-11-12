"""Router de recordatorios del panel (C-09, D7): solo recepción y admin; la odontóloga no ve teléfonos (C-08)."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import PermissionContext, require_recepcion_o_admin
from app.gestion.deps import get_reloj
from app.notificaciones import panel
from app.notificaciones.schemas import EstadoVisible, MarcarFallidoIn, RecordatorioOut, RecordatoriosOut
from app.pacientes.http import respuesta
from app.panel.schemas import ErrorPanelBody
from app.shared.db import get_session

router = APIRouter(prefix="/api/panel/recordatorios", tags=["recordatorios"],
                   dependencies=[Depends(require_recepcion_o_admin)])

_ERRORES = {
    401: {"description": "Sin token de acceso válido"},
    403: {"description": "Solo recepción y admin"},
}
_ERRORES_ESCRITURA = {
    **_ERRORES,
    404: {"model": ErrorPanelBody, "description": "`recordatorio_inexistente`"},
    409: {"model": ErrorPanelBody, "description": "`recordatorio_no_vigente`"},
}


@router.get("", response_model=RecordatoriosOut,
            summary="Recordatorios vigentes por avisar (por defecto pendientes y fallidos), con el link de WhatsApp",
            responses={**_ERRORES, 422: {"description": "`estado` fuera del catálogo"}})
async def listar(
    estado: Annotated[list[EstadoVisible] | None, Query(description="Uno o más estados; por defecto pendiente y fallido")] = None,
    session: AsyncSession = Depends(get_session),
    ahora: datetime = Depends(get_reloj),
) -> RecordatoriosOut:
    estados = tuple(estado) if estado else panel.ESTADOS_POR_DEFECTO
    return RecordatoriosOut(items=await panel.listar_recordatorios(session, ahora, estados))


@router.post("/{recordatorio_id}/enviado", response_model=RecordatorioOut,
             summary="Recepción abrió WhatsApp: marca el recordatorio como enviado (o actualiza la fecha del reenvío)",
             responses=_ERRORES_ESCRITURA)
async def marcar_enviado(
    recordatorio_id: int,
    contexto: PermissionContext = Depends(require_recepcion_o_admin),
    session: AsyncSession = Depends(get_session),
    ahora: datetime = Depends(get_reloj),
) -> RecordatorioOut | JSONResponse:
    try:
        return await panel.marcar_enviado(session, recordatorio_id, contexto.usuario_id, ahora)
    except panel.RecordatorioInexistenteError as exc:
        return respuesta(404, str(exc), "recordatorio_inexistente")
    except panel.RecordatorioNoVigenteError as exc:
        return respuesta(409, str(exc), "recordatorio_no_vigente")


@router.post("/{recordatorio_id}/fallido", response_model=RecordatorioOut,
             summary="Recepción no pudo avisar: marca el recordatorio como fallido con un motivo de la lista",
             responses={**_ERRORES_ESCRITURA, 422: {"description": "Motivo fuera de la lista"}})
async def marcar_fallido(
    recordatorio_id: int,
    data: MarcarFallidoIn,
    contexto: PermissionContext = Depends(require_recepcion_o_admin),
    session: AsyncSession = Depends(get_session),
) -> RecordatorioOut | JSONResponse:
    try:
        return await panel.marcar_fallido(session, recordatorio_id, contexto.usuario_id, data.motivo)
    except panel.RecordatorioInexistenteError as exc:
        return respuesta(404, str(exc), "recordatorio_inexistente")
    except panel.RecordatorioNoVigenteError as exc:
        return respuesta(409, str(exc), "recordatorio_no_vigente")
