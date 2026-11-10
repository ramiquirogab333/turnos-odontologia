"""Router del panel interno (C-08, D1): agenda, opciones, alta manual y cambios de estado.

Todas las rutas exigen un token de acceso válido. La lectura la pueden hacer los tres roles (la odontóloga ve solo lo
suyo); la escritura queda para recepción y admin (O5).
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import PermissionContext, get_current_user
from app.gestion.deps import get_notificador, get_reloj
from app.gestion.errores import FueraDePlazoError
from app.gestion.eventos import NotificadorTurnos
from app.catalogo.router import require_recepcion_o_admin
from app.pagos.errores import (
    MarcadoNoHabilitadoError,
    OperacionReintentableError,
    TurnoAjenoError,
    TurnoInexistenteError,
)
from app.pagos.estados import TransicionInvalidaError
from app.panel.schemas import (
    AgendaQuery,
    AgendaResponse,
    CambioEstadoResponse,
    ErrorPanelBody,
    OpcionesResponse,
    TurnoManualCreado,
    TurnoManualCreate,
)
from app.panel.service import (
    AgendaAjenaError,
    InicioPasadoError,
    SinAccesoAlPanelError,
    SinProfesionalAsociadoError,
    cancelar_turno_panel,
    consultar_agenda,
    consultar_opciones,
    crear_turno_manual,
    marcar_turno,
    resolver_alcance,
    zona_clinica,
)
from app.public.schemas import ReservaConflictoBody
from app.public.service import FueraDeDisponibilidadError, ReservaConflictoError
from app.shared.db import get_session

router = APIRouter(prefix="/api/panel", tags=["panel"])

_ERRORES_ACCESO = {
    401: {"description": "Sin token de acceso válido"},
    403: {"model": ErrorPanelBody, "description": "Sin permisos, sin profesional asociado o agenda ajena"},
}


def _prohibido(detail: str, motivo: str) -> JSONResponse:
    return JSONResponse(status_code=403, content=ErrorPanelBody(detail=detail, motivo=motivo).model_dump(mode="json"))


@router.get(
    "/agenda",
    response_model=AgendaResponse,
    summary="Agenda del día o de la semana (hora de la clínica), según el rol",
    responses={**_ERRORES_ACCESO, 422: {"description": "Parámetros inválidos o filtro por un id inexistente"}},
)
async def agenda(
    query: Annotated[AgendaQuery, Query()],
    contexto: PermissionContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    ahora: datetime = Depends(get_reloj),
) -> AgendaResponse | JSONResponse:
    try:
        alcance = await resolver_alcance(session, contexto)
        return await consultar_agenda(session, alcance, query, ahora)
    except SinAccesoAlPanelError as exc:
        return _prohibido(str(exc), "sin_acceso_al_panel")
    except SinProfesionalAsociadoError as exc:
        return _prohibido(str(exc), "sin_profesional_asociado")
    except AgendaAjenaError as exc:
        return _prohibido(str(exc), "agenda_ajena")


@router.get(
    "/agenda/opciones",
    response_model=OpcionesResponse,
    summary="Profesionales visibles, sillones activos y tratamientos para filtros y alta manual",
    responses=_ERRORES_ACCESO,
)
async def opciones(
    contexto: PermissionContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> OpcionesResponse | JSONResponse:
    try:
        alcance = await resolver_alcance(session, contexto)
    except SinAccesoAlPanelError as exc:
        return _prohibido(str(exc), "sin_acceso_al_panel")
    except SinProfesionalAsociadoError as exc:
        return _prohibido(str(exc), "sin_profesional_asociado")
    return await consultar_opciones(session, alcance)


@router.post(
    "/turnos",
    response_model=TurnoManualCreado,
    status_code=status.HTTP_201_CREATED,
    summary="Alta manual de un turno (recepción/admin): nace reservado y sin seña (O7)",
    responses={
        **_ERRORES_ACCESO,
        409: {"model": ReservaConflictoBody, "description": "Solape por profesional o sillón, con alternativas"},
        422: {"description": "Fuera de la disponibilidad, inicio pasado, datos inválidos o referencia inexistente"},
    },
)
async def alta_manual(
    data: TurnoManualCreate,
    contexto: PermissionContext = Depends(require_recepcion_o_admin),
    session: AsyncSession = Depends(get_session),
    ahora: datetime = Depends(get_reloj),
) -> TurnoManualCreado | JSONResponse:
    try:
        return await crear_turno_manual(session, data, contexto.usuario_id, ahora)
    except InicioPasadoError as exc:
        return JSONResponse(status_code=422, content={"detail": str(exc), "motivo": "inicio_pasado"})
    except FueraDeDisponibilidadError as exc:
        return JSONResponse(status_code=422, content={"detail": str(exc), "motivo": "fuera_de_disponibilidad"})
    except ReservaConflictoError as exc:
        return JSONResponse(status_code=409, content=ReservaConflictoBody(
            detail=f"Solape por {exc.motivo}", motivo=exc.motivo, alternativas=exc.alternativas).model_dump())


# ---------------------------------------------------------------------------
# Cambios de estado (D4): ausente, atendido y cancelar
# ---------------------------------------------------------------------------

_ERRORES_ESTADO = {
    **_ERRORES_ACCESO,
    404: {"description": "El turno no existe"},
    409: {"model": ErrorPanelBody,
          "description": "`transicion_invalida`, `marcado_no_habilitado` o `fuera_de_plazo`"},
    503: {"description": "Operación transitoria no completada: reintentar"},
}


def _rechazo_estado(exc: Exception) -> JSONResponse:
    """Traduce los errores de dominio de un cambio de estado a su respuesta HTTP."""
    zona = zona_clinica()
    if isinstance(exc, TurnoInexistenteError):
        return JSONResponse(status_code=404, content={"detail": "No encontramos ese turno"})
    if isinstance(exc, TurnoAjenoError):  # C-11 O15: el mismo cuerpo para "ajeno" e "inexistente"
        return _prohibido(str(exc), "turno_ajeno")
    if isinstance(exc, TransicionInvalidaError):
        return JSONResponse(status_code=409, content=ErrorPanelBody(
            detail=f"El turno está {exc.actual} y no se puede pasar a {exc.destino}",
            motivo="transicion_invalida").model_dump(mode="json"))
    if isinstance(exc, MarcadoNoHabilitadoError):
        return JSONResponse(status_code=409, content=ErrorPanelBody(
            detail="Todavía no se puede marcar este turno", motivo="marcado_no_habilitado",
            habilitado_desde=exc.habilitado_desde.astimezone(zona)).model_dump(mode="json"))
    if isinstance(exc, FueraDePlazoError):
        return JSONResponse(status_code=409, content=ErrorPanelBody(
            detail="Faltan menos de 24 h: el turno ya no se puede cancelar desde el panel",
            motivo="fuera_de_plazo", limite_cambios=exc.limite_cambios.astimezone(zona)).model_dump(mode="json"))
    return JSONResponse(status_code=503, content={"detail": "reintentar"})


_ERRORES_DE_ESTADO = (TurnoInexistenteError, TurnoAjenoError, TransicionInvalidaError, MarcadoNoHabilitadoError, FueraDePlazoError,
                      OperacionReintentableError)


@router.post(
    "/turnos/{turno_id}/ausente",
    response_model=CambioEstadoResponse,
    summary="Marca el turno como ausente (desde el inicio más la tolerancia); la seña no se reembolsa (R9)",
    responses=_ERRORES_ESTADO,
)
async def marcar_ausente(
    turno_id: int,
    contexto: PermissionContext = Depends(require_recepcion_o_admin),
    session: AsyncSession = Depends(get_session),
    ahora: datetime = Depends(get_reloj),
) -> CambioEstadoResponse | JSONResponse:
    try:
        r = await marcar_turno(session, turno_id, "ausente", contexto.usuario_id, ahora)
    except _ERRORES_DE_ESTADO as exc:
        return _rechazo_estado(exc)
    return CambioEstadoResponse(turno_id=r.turno_id, estado=r.estado_turno, estado_sena=r.estado_pago)


@router.post(
    "/turnos/{turno_id}/atendido",
    response_model=CambioEstadoResponse,
    summary="Marca el turno como atendido (desde las 00:00 del día local del turno); sigue ocupando el horario. Recepción/admin cualquier turno; la odontóloga, solo los de su profesional (`turno_ajeno`, O15)",
    responses=_ERRORES_ESTADO,
)
async def marcar_atendido(
    turno_id: int,
    contexto: PermissionContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    ahora: datetime = Depends(get_reloj),
) -> CambioEstadoResponse | JSONResponse:
    # C-11 O15: la única escritura de la odontóloga. Recepción/admin sin restricción; ella solo sus turnos.
    try:
        alcance = await resolver_alcance(session, contexto)
        r = await marcar_turno(session, turno_id, "atendido", contexto.usuario_id, ahora,
                               profesional_requerido=alcance.profesional_id)
    except SinAccesoAlPanelError as exc:
        return _prohibido(str(exc), "sin_acceso_al_panel")
    except SinProfesionalAsociadoError as exc:
        return _prohibido(str(exc), "sin_profesional_asociado")
    except _ERRORES_DE_ESTADO as exc:
        return _rechazo_estado(exc)
    return CambioEstadoResponse(turno_id=r.turno_id, estado=r.estado_turno, estado_sena=r.estado_pago)


@router.post(
    "/turnos/{turno_id}/cancelar",
    response_model=CambioEstadoResponse,
    summary="Cancela el turno: 24 h de anticipación si ya ocupa agenda; una pre-reserva, en cualquier momento",
    responses=_ERRORES_ESTADO,
)
async def cancelar(
    turno_id: int,
    contexto: PermissionContext = Depends(require_recepcion_o_admin),
    session: AsyncSession = Depends(get_session),
    ahora: datetime = Depends(get_reloj),
    notificador: NotificadorTurnos = Depends(get_notificador),
) -> CambioEstadoResponse | JSONResponse:
    try:
        r = await cancelar_turno_panel(session, turno_id, contexto.usuario_id, ahora, notificador)
    except _ERRORES_DE_ESTADO as exc:
        return _rechazo_estado(exc)
    return CambioEstadoResponse(turno_id=r.turno_id, estado=r.estado_turno, estado_sena=r.estado_pago)
