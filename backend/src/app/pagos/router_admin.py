"""Router admin de la seña (C-06): acreditar transferencias y configurar (recepcion/admin; R15).

- POST /api/admin/pagos-sena/{id}/acreditar: acredita a mano una transferencia (RN-SN-08).
- GET/PUT /api/admin/config/sena: porcentaje, medios, textos, plazos y datos de transferencia.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import PermissionContext
from app.catalogo.router import require_recepcion_o_admin
from app.pagos.config import obtener_configuracion
from app.pagos.errores import OperacionReintentableError, PagoNoAcreditableError, PagoNoEncontradoError
from app.pagos.models import ConfiguracionSena, PagoSena
from app.pagos.schemas import AcreditacionResponse, ConfiguracionSenaRead, ConfiguracionSenaUpdate
from app.pagos.service import acreditar_transferencia, actualizar_configuracion
from app.shared.db import get_session
from app.turnos.models import Turno

router = APIRouter(prefix="/api/admin", tags=["admin-pagos"])


@router.post(
    "/pagos-sena/{pago_id}/acreditar",
    response_model=AcreditacionResponse,
    summary="Acredita a mano una seña pagada por transferencia",
    responses={
        403: {"description": "Rol sin permiso (se requiere recepcion o admin)"},
        404: {"description": "Pago inexistente"},
        409: {"description": "No es una transferencia pendiente y vigente"},
    },
)
async def acreditar(
    pago_id: int,
    session: AsyncSession = Depends(get_session),
    context: PermissionContext = Depends(require_recepcion_o_admin),
) -> AcreditacionResponse | JSONResponse:
    """Misma regla de anti-solape que el webhook; deja auditado quién lo hizo (RN-GL-01)."""
    try:
        resultado = await acreditar_transferencia(session, pago_id, context.usuario_id)
    except PagoNoEncontradoError:
        return JSONResponse(status_code=404, content={"detail": "Pago no encontrado"})
    except PagoNoAcreditableError as exc:
        return JSONResponse(status_code=409, content={"detail": str(exc), "motivo": exc.motivo})
    except OperacionReintentableError:
        return JSONResponse(status_code=503, content={"detail": "Reintentá en unos instantes"})
    pago = (await session.execute(select(PagoSena).where(PagoSena.id == pago_id))).scalar_one()
    turno = (await session.execute(select(Turno).where(Turno.id == pago.turno_id))).scalar_one()
    return AcreditacionResponse(
        pago_id=resultado.pago_id, turno_id=resultado.turno_id, efecto=resultado.efecto,
        estado_pago=pago.estado, estado_turno=turno.estado)


@router.get(
    "/config/sena",
    response_model=ConfiguracionSenaRead,
    summary="Configuración vigente de la seña",
    responses={403: {"description": "Rol sin permiso"}},
)
async def leer_configuracion(
    session: AsyncSession = Depends(get_session),
    _: PermissionContext = Depends(require_recepcion_o_admin),
) -> ConfiguracionSena:
    return await obtener_configuracion(session)


@router.put(
    "/config/sena",
    response_model=ConfiguracionSenaRead,
    summary="Actualiza la configuración de la seña (auditado)",
    responses={403: {"description": "Rol sin permiso"}, 422: {"description": "Valores fuera de rango"}},
)
async def actualizar(
    data: ConfiguracionSenaUpdate,
    session: AsyncSession = Depends(get_session),
    context: PermissionContext = Depends(require_recepcion_o_admin),
) -> ConfiguracionSena:
    return await actualizar_configuracion(session, data.model_dump(), context.usuario_id)
