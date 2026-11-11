"""Router de la caja (C-12, D1): todo bajo ``/api/panel/caja`` y solo para recepción y admin (O15)."""

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import PermissionContext, require_recepcion_o_admin, require_role
from app.caja import cierres, service
from app.caja.schemas import (
    AnularCierreIn,
    CajaOut,
    CierreCreateIn,
    CierreDetalleOut,
    CierreOut,
    CierreResumenOut,
    DevolucionIn,
    DevolucionOut,
    PendienteOut,
    RechazoOut,
    LiquidacionOut,
    RangoFechas,
)
from app.pagos import devoluciones
from app.panel.schemas import ErrorPanelBody
from app.gestion.deps import get_reloj
from app.shared.db import get_session

router = APIRouter(prefix="/api/panel/caja", tags=["caja"])

_ERRORES_ACCESO = {
    401: {"description": "Sin token de acceso válido"},
    403: {"description": "Solo recepción y admin"},
}


@router.get(
    "",
    response_model=CajaOut,
    summary="Caja de un día de la clínica por concepto y medio (sin `dia`: hoy)",
    responses={**_ERRORES_ACCESO, 422: {"description": "`dia` inválido"}},
)
async def caja_del_dia(
    dia: Annotated[date | None, Query(description="AAAA-MM-DD, día de la clínica")] = None,
    contexto: PermissionContext = Depends(require_recepcion_o_admin),
    session: AsyncSession = Depends(get_session),
    ahora: datetime = Depends(get_reloj),
) -> CajaOut:
    return await service.consultar_caja(session, contexto.usuario_id, dia or service.dia_actual(ahora))


# ---------------------------------------------------------------------------
# Cierres (un vigente por día; la API no edita ni borra) y liquidación
# ---------------------------------------------------------------------------

_ERRORES_CIERRE = {
    **_ERRORES_ACCESO,
    404: {"model": ErrorPanelBody, "description": "`cierre_inexistente`"},
    409: {"model": ErrorPanelBody, "description": "`dia_no_terminado`, `dia_ya_cerrado` o `transicion_invalida`"},
    422: {"description": "Cuerpo o rango inválido (los importes no se aceptan del cliente)"},
}


@router.post("/cierres", response_model=CierreOut, status_code=status.HTTP_201_CREATED,
             summary="Cierra la caja de un día terminado (desde las 00:15 del día siguiente); los importes los calcula el servidor",
             responses=_ERRORES_CIERRE)
async def cerrar_caja(
    data: CierreCreateIn,
    contexto: PermissionContext = Depends(require_recepcion_o_admin),
    session: AsyncSession = Depends(get_session),
    ahora: datetime = Depends(get_reloj),
) -> CierreOut:
    return await cierres.cerrar_dia(session, contexto.usuario_id, data.dia, data.observaciones, ahora)


@router.get("/cierres", response_model=list[CierreResumenOut],
            summary="Cierres cuyo día está en el rango (hasta 366 días), del más reciente al más antiguo",
            responses=_ERRORES_CIERRE)
async def listar_cierres(
    rango: Annotated[RangoFechas, Query()],
    contexto: PermissionContext = Depends(require_recepcion_o_admin),
    session: AsyncSession = Depends(get_session),
) -> list[CierreResumenOut]:
    return await cierres.listar_cierres(session, rango)


@router.get("/cierres/{cierre_id}", response_model=CierreDetalleOut,
            summary="Un cierre con sus líneas y `cuadra` (recalculado contra los movimientos del día)",
            responses=_ERRORES_CIERRE)
async def obtener_cierre(
    cierre_id: int,
    contexto: PermissionContext = Depends(require_recepcion_o_admin),
    session: AsyncSession = Depends(get_session),
) -> CierreDetalleOut:
    return await cierres.consultar_cierre(session, cierre_id)


@router.post("/cierres/{cierre_id}/anular", response_model=CierreOut,
             summary="Anula un cierre vigente con motivo (solo admin): el día vuelve a estar abierto",
             responses=_ERRORES_CIERRE)
async def anular_cierre(
    cierre_id: int,
    data: AnularCierreIn,
    contexto: PermissionContext = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
    ahora: datetime = Depends(get_reloj),
) -> CierreOut:
    return await cierres.anular_cierre(session, contexto.usuario_id, cierre_id, data.motivo, ahora)


@router.get("/liquidacion", response_model=LiquidacionOut,
            summary="Consolidado por medio de pago de los cierres vigentes del rango, con los días sin cerrar",
            responses=_ERRORES_CIERRE)
async def liquidacion(
    rango: Annotated[RangoFechas, Query()],
    contexto: PermissionContext = Depends(require_recepcion_o_admin),
    session: AsyncSession = Depends(get_session),
) -> LiquidacionOut:
    return await cierres.liquidacion(session, rango)


# ---------------------------------------------------------------------------
# Pendientes de la seña: revisiones, devoluciones y excedentes de Mercado Pago
# ---------------------------------------------------------------------------

_ERRORES_PENDIENTES = {
    **_ERRORES_ACCESO,
    404: {"model": ErrorPanelBody, "description": "`pago_inexistente`"},
    409: {"model": ErrorPanelBody,
          "description": "`no_esta_en_revision`, `no_es_devolucion_pendiente` o `caja_cerrada`"},
    422: {"description": "Referencia inválida, importe enviado o fecha futura / anterior a la recepción"},
}


@router.get("/pendientes", response_model=list[PendienteOut],
            summary="Pagos en revisión y devoluciones pendientes (señas y excedentes de Mercado Pago), del más antiguo al más nuevo",
            responses=_ERRORES_ACCESO)
async def pendientes(
    contexto: PermissionContext = Depends(require_recepcion_o_admin),
    session: AsyncSession = Depends(get_session),
) -> list[PendienteOut]:
    return await devoluciones.listar_pendientes(session)


@router.post("/revisiones/{pago_id}/rechazar", response_model=RechazoOut,
             summary="Rechaza un pago en revisión: queda a reembolsar y el turno no cambia",
             responses={**_ERRORES_PENDIENTES, 503: {"description": "Operación transitoria: reintentar"}})
async def rechazar_revision(
    pago_id: int,
    contexto: PermissionContext = Depends(require_recepcion_o_admin),
    session: AsyncSession = Depends(get_session),
    ahora: datetime = Depends(get_reloj),
) -> RechazoOut:
    return await devoluciones.rechazar_revision(session, contexto.usuario_id, pago_id, ahora)


@router.post("/devoluciones/senas/{pago_id}", response_model=DevolucionOut,
             summary="Registra la devolución hecha de una seña a reembolsar (estado final `reembolsado`)",
             responses=_ERRORES_PENDIENTES)
async def devolver_sena(
    pago_id: int,
    data: DevolucionIn,
    contexto: PermissionContext = Depends(require_recepcion_o_admin),
    session: AsyncSession = Depends(get_session),
    ahora: datetime = Depends(get_reloj),
) -> DevolucionOut:
    return await devoluciones.registrar_devolucion_sena(
        session, contexto.usuario_id, pago_id, data.referencia, data.fecha, ahora)


@router.post("/devoluciones/excedentes/{aprobacion_id}", response_model=DevolucionOut,
             summary="Registra la devolución de un pago excedente de Mercado Pago (no mueve la caja)",
             responses=_ERRORES_PENDIENTES)
async def devolver_excedente(
    aprobacion_id: int,
    data: DevolucionIn,
    contexto: PermissionContext = Depends(require_recepcion_o_admin),
    session: AsyncSession = Depends(get_session),
    ahora: datetime = Depends(get_reloj),
) -> DevolucionOut:
    return await devoluciones.registrar_devolucion_excedente(
        session, contexto.usuario_id, aprobacion_id, data.referencia, data.fecha, ahora)
