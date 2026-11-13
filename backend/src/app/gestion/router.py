"""Router público de gestión del turno (C-07): consulta, cancelación y reprogramación (R15, R16).

El código de gestión viaja SIEMPRE en la cabecera ``X-Codigo-Gestion`` (nunca en la ruta ni en la query) para que
no quede en logs ni en el ``Referer`` (decisión O1).
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.limites import (
    RESPUESTA_429_OPENAPI,
    limitar_publico_escritura,
    limitar_publico_lectura,
)
from app.gestion.deps import get_notificador, get_reloj
from app.gestion.errores import (
    FueraDePlazoError,
    GestionNoEncontradaError,
    HorarioInvalidoError,
    SenaPendienteError,
    TurnoIniciadoError,
    TurnoNoModificableError,
)
from app.gestion.eventos import NotificadorTurnos
from app.gestion.schemas import (
    CancelacionResponse,
    ConfirmacionResponse,
    ErrorGestionBody,
    GestionTurnoResponse,
    ReprogramacionResponse,
    ReprogramarRequest,
)
from app.gestion.service import (
    cancelar_turno_publico,
    confirmar_turno_publico,
    consultar_gestion,
    reprogramar_turno_publico,
    zona_clinica,
)
from app.pagos.errores import OperacionReintentableError
from app.public.schemas import ReservaConflictoBody
from app.public.service import FueraDeDisponibilidadError, ReservaConflictoError
from app.shared.db import get_session

router = APIRouter(prefix="/api/public/gestion", tags=["gestion"])

CodigoGestion = Annotated[str | None, Header(alias="X-Codigo-Gestion")]

_NO_ENCONTRADO = {"detail": "No encontramos un turno con ese código"}


def _respuesta_404() -> JSONResponse:
    return JSONResponse(status_code=404, content=_NO_ENCONTRADO)


def _respuesta_fuera_de_plazo(exc: FueraDePlazoError) -> JSONResponse:
    limite = exc.limite_cambios.astimezone(zona_clinica())
    return JSONResponse(status_code=409, content=ErrorGestionBody(
        detail=("Ya no podés cancelar ni cambiar el turno online porque faltan menos de 24 h. "
                "Comunicate con la clínica."),
        motivo="fuera_de_plazo", limite_cambios=limite).model_dump(mode="json"))


def _respuesta_no_modificable() -> JSONResponse:
    return JSONResponse(status_code=409, content=ErrorGestionBody(
        detail="Este turno ya no se puede modificar.", motivo="turno_no_modificable").model_dump(mode="json"))


def _respuesta_reintentar() -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": "reintentar"})


@router.get(
    "",
    dependencies=[Depends(limitar_publico_lectura)],
    response_model=GestionTurnoResponse,
    summary="Datos del turno para gestionarlo (cancelar o cambiar el horario)",
    responses={**RESPUESTA_429_OPENAPI,
        404: {"description": "Código de gestión ausente, desconocido o de un turno sin código"}},
)
async def consultar(
    codigo: CodigoGestion = None,
    session: AsyncSession = Depends(get_session),
    ahora: datetime = Depends(get_reloj),
) -> GestionTurnoResponse | JSONResponse:
    try:
        datos = await consultar_gestion(session, codigo, ahora=ahora)
    except GestionNoEncontradaError:
        return _respuesta_404()
    return GestionTurnoResponse.model_validate(datos)


@router.post(
    "/confirmar",
    dependencies=[Depends(limitar_publico_escritura)],
    response_model=ConfirmacionResponse,
    summary="Confirma la asistencia al turno reservado (sin ventana de 24 h)",
    responses={**RESPUESTA_429_OPENAPI,
        
        404: {"description": "Código de gestión ausente o desconocido"},
        409: {"model": ErrorGestionBody, "description": "Seña pendiente, turno no modificable o ya iniciado"},
        503: {"description": "Operación transitoria no completada: reintentar"},
    },
)
async def confirmar(
    codigo: CodigoGestion = None,
    session: AsyncSession = Depends(get_session),
    ahora: datetime = Depends(get_reloj),
) -> ConfirmacionResponse | JSONResponse:
    try:
        datos = await confirmar_turno_publico(session, codigo, ahora=ahora)
    except GestionNoEncontradaError:
        return _respuesta_404()
    except TurnoNoModificableError:
        return _respuesta_no_modificable()
    except SenaPendienteError as exc:
        return JSONResponse(status_code=409, content=ErrorGestionBody(
            detail=str(exc), motivo="sena_pendiente").model_dump(mode="json"))
    except TurnoIniciadoError:
        return JSONResponse(status_code=409, content=ErrorGestionBody(
            detail="Este turno ya empezó, no se puede confirmar.", motivo="turno_iniciado").model_dump(mode="json"))
    except OperacionReintentableError:
        return _respuesta_reintentar()
    return ConfirmacionResponse.model_validate(datos)


@router.post(
    "/cancelar",
    dependencies=[Depends(limitar_publico_escritura)],
    response_model=CancelacionResponse,
    summary="Cancela el turno del paciente (24 h de anticipación si ya tiene seña acreditada)",
    responses={**RESPUESTA_429_OPENAPI,
        
        404: {"description": "Código de gestión ausente o desconocido"},
        409: {"model": ErrorGestionBody, "description": "Fuera de plazo o turno no modificable"},
        503: {"description": "Operación transitoria no completada: reintentar"},
    },
)
async def cancelar(
    codigo: CodigoGestion = None,
    session: AsyncSession = Depends(get_session),
    ahora: datetime = Depends(get_reloj),
    notificador: NotificadorTurnos = Depends(get_notificador),
) -> CancelacionResponse | JSONResponse:
    try:
        r = await cancelar_turno_publico(session, codigo, ahora=ahora, notificador=notificador)
    except GestionNoEncontradaError:
        return _respuesta_404()
    except FueraDePlazoError as exc:
        return _respuesta_fuera_de_plazo(exc)
    except TurnoNoModificableError:
        return _respuesta_no_modificable()
    except OperacionReintentableError:
        return _respuesta_reintentar()
    return CancelacionResponse(estado="cancelado", estado_sena=r.estado_pago)


@router.post(
    "/reprogramar",
    dependencies=[Depends(limitar_publico_escritura)],
    response_model=ReprogramacionResponse,
    status_code=status.HTTP_200_OK,
    summary="Mueve el turno a otro horario libre de la misma profesional (24 h de anticipación)",
    responses={**RESPUESTA_429_OPENAPI,
        
        404: {"description": "Código de gestión ausente o desconocido"},
        409: {"description": "Fuera de plazo, seña pendiente, turno no modificable u horario ocupado"},
        422: {"description": "Horario fuera de la disponibilidad, igual al actual o pasado"},
        503: {"description": "Operación transitoria no completada: reintentar"},
    },
)
async def reprogramar(
    data: ReprogramarRequest,
    codigo: CodigoGestion = None,
    session: AsyncSession = Depends(get_session),
    ahora: datetime = Depends(get_reloj),
    notificador: NotificadorTurnos = Depends(get_notificador),
) -> ReprogramacionResponse | JSONResponse:
    try:
        r = await reprogramar_turno_publico(session, codigo, data.inicio, ahora=ahora, notificador=notificador)
    except GestionNoEncontradaError:
        return _respuesta_404()
    except FueraDePlazoError as exc:
        return _respuesta_fuera_de_plazo(exc)
    except TurnoNoModificableError:
        return _respuesta_no_modificable()
    except SenaPendienteError as exc:
        return JSONResponse(status_code=409, content=ErrorGestionBody(
            detail=str(exc), motivo="sena_pendiente").model_dump(mode="json"))
    except FueraDeDisponibilidadError as exc:
        return JSONResponse(status_code=422, content={"detail": str(exc), "motivo": "fuera_de_disponibilidad"})
    except HorarioInvalidoError as exc:
        return JSONResponse(status_code=422, content={"detail": str(exc), "motivo": exc.motivo})
    except ReservaConflictoError as exc:
        return JSONResponse(status_code=409, content=ReservaConflictoBody(
            detail=f"Solape por {exc.motivo}", motivo=exc.motivo, alternativas=exc.alternativas).model_dump())
    except OperacionReintentableError:
        return _respuesta_reintentar()
    return ReprogramacionResponse.model_validate(r)
