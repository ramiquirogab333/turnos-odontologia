"""Router público de la seña (C-06): inicio y consulta con el código de gestión (R15, R16).

- POST /api/public/turnos/{id}/sena: inicia (201) o reanuda (200) el pago de la seña.
- GET  /api/public/turnos/{id}/sena: estado del turno y del último pago, sin datos de contacto.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.limites import (
    RESPUESTA_429_OPENAPI,
    limitar_publico_escritura,
    limitar_publico_lectura,
)
from app.pagos.deps import get_pasarela
from app.pagos.errores import (
    MedioNoHabilitadoError,
    SenaNoEncontradaError,
    SenaNoRequeridaError,
    TurnoNoPendienteError,
)
from app.pagos.models import ConfiguracionSena, PagoSena
from app.pagos.pasarela import PasarelaNoDisponibleError, PasarelaPagos
from app.pagos.schemas import EstadoSenaResponse, IniciarSenaRequest, IniciarSenaResponse
from app.pagos.service import consultar_sena, iniciar_sena
from app.public.schemas import ReservaConflictoBody
from app.public.service import ReservaConflictoError
from app.shared.db import get_session

router = APIRouter(prefix="/api/public/turnos", tags=["pagos"])

CodigoGestion = Annotated[str | None, Header(alias="X-Codigo-Gestion")]


def _datos_pago(pago: PagoSena | None, config: ConfiguracionSena) -> dict[str, Any]:
    """Campos de pago comunes; los datos bancarios solo mientras la transferencia está pendiente."""
    transferencia = pago is not None and pago.medio == "transferencia" and pago.estado == "pendiente"
    return {
        "pago_id": pago.id if pago else None,
        "medio": pago.medio if pago else None,
        "referencia_externa": pago.referencia_externa if pago else None,
        "checkout_url": pago.checkout_url if pago else None,
        "alias": config.transferencia_alias if transferencia else None,
        "cbu": config.transferencia_cbu if transferencia else None,
        "titular": config.transferencia_titular if transferencia else None,
        "referencia_concepto": pago.referencia_externa if transferencia and pago else None,
        "texto_politica_reembolso": config.texto_politica_reembolso,
    }


@router.post(
    "/{turno_id}/sena",
    dependencies=[Depends(limitar_publico_escritura)],
    response_model=IniciarSenaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Inicia la seña de un turno en espera (Mercado Pago o transferencia)",
    responses={**RESPUESTA_429_OPENAPI,
        
        200: {"model": IniciarSenaResponse, "description": "Reintento con el mismo medio: mismo pago pendiente"},
        404: {"description": "Código de gestión ausente o ajeno"},
        409: {"model": ReservaConflictoBody, "description": "Turno no vigente u horario ya tomado"},
        422: {"description": "Medio deshabilitado o inexistente"},
        502: {"description": "La pasarela de pagos no respondió"},
    },
)
async def iniciar(
    turno_id: int,
    data: IniciarSenaRequest,
    response: Response,
    codigo: CodigoGestion = None,
    session: AsyncSession = Depends(get_session),
    pasarela: PasarelaPagos = Depends(get_pasarela),
) -> IniciarSenaResponse | JSONResponse:
    """Crea el pago pendiente y devuelve cómo completarlo (checkout o datos de transferencia)."""
    try:
        resultado = await iniciar_sena(session, turno_id, codigo, data.medio, pasarela)
    except SenaNoEncontradaError:
        return JSONResponse(status_code=404, content={"detail": "Turno no encontrado"})
    except TurnoNoPendienteError as exc:
        return JSONResponse(status_code=409, content={"detail": str(exc), "motivo": "estado_invalido"})
    except ReservaConflictoError as exc:
        return JSONResponse(status_code=409, content=ReservaConflictoBody(
            detail=f"Solape por {exc.motivo}", motivo=exc.motivo, alternativas=exc.alternativas).model_dump())
    except MedioNoHabilitadoError as exc:
        return JSONResponse(status_code=422, content={
            "detail": f"Medio no habilitado: {exc.medio}", "medios_habilitados": exc.habilitados})
    except SenaNoRequeridaError as exc:
        return JSONResponse(status_code=409, content={"detail": str(exc), "motivo": "sena_no_requerida"})
    except PasarelaNoDisponibleError:
        return JSONResponse(status_code=502, content={
            "detail": "No pudimos conectar con Mercado Pago. Probá de nuevo en unos minutos."})
    if not resultado.creado:
        response.status_code = status.HTTP_200_OK
    pago = resultado.pago
    return IniciarSenaResponse(
        turno_id=resultado.turno.id, estado=pago.estado, monto=pago.monto, vence_en=pago.vence_en,
        **_datos_pago(pago, resultado.config))


@router.get(
    "/{turno_id}/sena",
    dependencies=[Depends(limitar_publico_lectura)],
    response_model=EstadoSenaResponse,
    summary="Estado de la seña de un turno",
    responses={**RESPUESTA_429_OPENAPI,
        404: {"description": "Código de gestión ausente o ajeno"}},
)
async def consultar(
    turno_id: int,
    codigo: CodigoGestion = None,
    session: AsyncSession = Depends(get_session),
) -> EstadoSenaResponse | JSONResponse:
    """Estado del turno y del último pago, para que la pantalla sepa cuándo terminó la espera."""
    try:
        r = await consultar_sena(session, turno_id, codigo)
    except SenaNoEncontradaError:
        return JSONResponse(status_code=404, content={"detail": "Turno no encontrado"})
    pago: PagoSena | None = r["pago"]
    return EstadoSenaResponse(
        turno_id=r["turno"].id, estado_turno=r["turno"].estado, estado_pago=pago.estado if pago else None,
        monto=r["monto"], vence_en=r["vence_en"], vencida=r["vencida"],
        medios_habilitados=r["medios_habilitados"], inicio=r["turno"].inicio, fin=r["turno"].fin,
        tratamiento_nombre=r["tratamiento_nombre"], profesional_nombre=r["profesional_nombre"],
        **_datos_pago(pago, r["config"]))
