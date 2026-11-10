"""Router clínico del panel (C-11, D1): odontograma, presupuestos y pagos de presupuesto.

El odontograma solo tiene ``GET`` y ``POST``: no existe ninguna ruta que modifique o borre un registro (RN-CL-01).
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import PermissionContext, get_current_user, require_recepcion_o_admin
from app.clinica import service_odontograma, service_pagos, service_presupuestos
from app.clinica.schemas import (
    AnulacionIn,
    HistorialOdontogramaOut,
    HistorialQuery,
    LoteOdontogramaIn,
    LoteOdontogramaOut,
    OdontogramaVigenteOut,
    PagoCreate,
    PagoRegistradoOut,
    PagosPresupuestoOut,
    PresupuestoCreate,
    PresupuestoOut,
    PresupuestoUpdate,
    PresupuestoVistaClinicaOut,
    TransicionIn,
)
from app.gestion.deps import get_reloj
from app.panel.schemas import ErrorPanelBody
from app.shared.db import get_session

router = APIRouter(prefix="/api/panel", tags=["clinica"])

_ERRORES = {
    401: {"description": "Sin token de acceso válido"},
    403: {"model": ErrorPanelBody, "description": "Sin permisos, `paciente_ajeno` o `acceso_clinico_vencido`"},
    404: {"model": ErrorPanelBody, "description": "Paciente inexistente"},
}


@router.post("/pacientes/{paciente_id}/odontograma", response_model=LoteOdontogramaOut,
             status_code=status.HTTP_201_CREATED,
             summary="Registra un lote de 1 a 64 hallazgos (solo alta; todo o nada)",
             responses={**_ERRORES, 422: {"description": "Pieza, cara o estado inválidos, o lote fuera de 1-64"}})
async def registrar_odontograma(
    paciente_id: int,
    lote: LoteOdontogramaIn,
    contexto: PermissionContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    ahora: datetime = Depends(get_reloj),
) -> LoteOdontogramaOut:
    return await service_odontograma.registrar_lote(session, contexto, paciente_id, lote, ahora)


@router.get("/pacientes/{paciente_id}/odontograma", response_model=OdontogramaVigenteOut,
            summary="Estado vigente por pieza y cara, derivado del historial", responses=_ERRORES)
async def odontograma_vigente(
    paciente_id: int,
    contexto: PermissionContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    ahora: datetime = Depends(get_reloj),
) -> OdontogramaVigenteOut:
    return await service_odontograma.estado_vigente(session, contexto, paciente_id, ahora)


@router.get("/pacientes/{paciente_id}/odontograma/historial", response_model=HistorialOdontogramaOut,
            summary="Historial completo, del más reciente al más antiguo, paginado (máx. 200)",
            responses={**_ERRORES, 422: {"description": "`limite` fuera de 1-200"}})
async def odontograma_historial(
    paciente_id: int,
    query: Annotated[HistorialQuery, Query()],
    contexto: PermissionContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    ahora: datetime = Depends(get_reloj),
) -> HistorialOdontogramaOut:
    return await service_odontograma.historial(session, contexto, paciente_id, query, ahora)


# ---------------------------------------------------------------------------
# Presupuestos (O4: la odontóloga solo lee, sin pagos; las escrituras son de recepción y admin)
# ---------------------------------------------------------------------------

_ERRORES_ESCRITURA = {
    **_ERRORES,
    409: {"model": ErrorPanelBody,
          "description": "`transicion_invalida`, `presupuesto_no_editable` o `presupuesto_con_pagos`"},
    422: {"description": "Cuerpo inválido, tratamiento inexistente u `obra_social_inactiva`"},
}


@router.post("/pacientes/{paciente_id}/presupuestos", response_model=PresupuestoOut,
             status_code=status.HTTP_201_CREATED,
             summary="Crea un presupuesto en borrador; los importes los calcula el servidor",
             responses=_ERRORES_ESCRITURA)
async def crear_presupuesto(
    paciente_id: int,
    data: PresupuestoCreate,
    contexto: PermissionContext = Depends(require_recepcion_o_admin),
    session: AsyncSession = Depends(get_session),
) -> PresupuestoOut:
    return await service_presupuestos.crear_presupuesto(session, contexto.usuario_id, paciente_id, data)


@router.get("/pacientes/{paciente_id}/presupuestos", response_model=list[PresupuestoOut | PresupuestoVistaClinicaOut],
            summary="Presupuestos del paciente (la odontóloga de sus pacientes, sin pagos ni saldo)",
            responses=_ERRORES)
async def listar_presupuestos(
    paciente_id: int,
    contexto: PermissionContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    ahora: datetime = Depends(get_reloj),
) -> list[PresupuestoOut | PresupuestoVistaClinicaOut]:
    return await service_presupuestos.listar_presupuestos(session, contexto, paciente_id, ahora)


@router.get("/pacientes/{paciente_id}/presupuestos/{presupuesto_id}",
            response_model=PresupuestoOut | PresupuestoVistaClinicaOut,
            summary="Detalle de un presupuesto del paciente (404 si es de otro)", responses=_ERRORES)
async def obtener_presupuesto(
    paciente_id: int,
    presupuesto_id: int,
    contexto: PermissionContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    ahora: datetime = Depends(get_reloj),
) -> PresupuestoOut | PresupuestoVistaClinicaOut:
    return await service_presupuestos.obtener_presupuesto(session, contexto, paciente_id, presupuesto_id, ahora)


@router.put("/pacientes/{paciente_id}/presupuestos/{presupuesto_id}", response_model=PresupuestoOut,
            summary="Reemplaza líneas, obra social y notas de un borrador y recalcula todo",
            responses=_ERRORES_ESCRITURA)
async def editar_presupuesto(
    paciente_id: int,
    presupuesto_id: int,
    data: PresupuestoUpdate,
    contexto: PermissionContext = Depends(require_recepcion_o_admin),
    session: AsyncSession = Depends(get_session),
) -> PresupuestoOut:
    return await service_presupuestos.editar_presupuesto(
        session, contexto.usuario_id, paciente_id, presupuesto_id, data)


def _transicion(accion: str, destino: str) -> None:
    """Registra POST .../presupuestos/{id}/{accion}: presentar, aceptar o rechazar (cuerpo vacío)."""

    async def _endpoint(
        paciente_id: int,
        presupuesto_id: int,
        cuerpo: TransicionIn | None = None,
        contexto: PermissionContext = Depends(require_recepcion_o_admin),
        session: AsyncSession = Depends(get_session),
        ahora: datetime = Depends(get_reloj),
    ) -> PresupuestoOut:
        return await service_presupuestos.transicionar_presupuesto(
            session, contexto.usuario_id, paciente_id, presupuesto_id, destino, ahora)

    router.add_api_route(f"/pacientes/{{paciente_id}}/presupuestos/{{presupuesto_id}}/{accion}", _endpoint,
                         methods=["POST"], response_model=PresupuestoOut, name=f"{accion}_presupuesto",
                         summary=f"Pasa el presupuesto a {destino} (sin facturación electrónica, RN-PG-03)",
                         responses=_ERRORES_ESCRITURA)


for _accion, _destino in (("presentar", "presentado"), ("aceptar", "aceptado"), ("rechazar", "rechazado")):
    _transicion(_accion, _destino)


@router.post("/pacientes/{paciente_id}/presupuestos/{presupuesto_id}/anular", response_model=PresupuestoOut,
             summary="Anula el presupuesto con motivo; un aceptado con pagos registrados no se anula",
             responses=_ERRORES_ESCRITURA)
async def anular_presupuesto(
    paciente_id: int,
    presupuesto_id: int,
    cuerpo: AnulacionIn,
    contexto: PermissionContext = Depends(require_recepcion_o_admin),
    session: AsyncSession = Depends(get_session),
    ahora: datetime = Depends(get_reloj),
) -> PresupuestoOut:
    return await service_presupuestos.transicionar_presupuesto(
        session, contexto.usuario_id, paciente_id, presupuesto_id, "anulado", ahora, cuerpo.motivo)


# ---------------------------------------------------------------------------
# Pagos de presupuesto (O3, O4, O12): solo recepción y admin, aunque la odontóloga sea la del paciente
# ---------------------------------------------------------------------------

_ERRORES_PAGO = {
    **_ERRORES,
    409: {"model": ErrorPanelBody,
          "description": "`presupuesto_no_aceptado`, `monto_excede_saldo` (con `saldo`), `referencia_duplicada` "
                         "o `transicion_invalida`"},
    422: {"description": "Medio, monto, fecha de cobro o motivo inválidos"},
}
_RUTA_PAGOS = "/pacientes/{paciente_id}/presupuestos/{presupuesto_id}/pagos"


@router.post(_RUTA_PAGOS, response_model=PagoRegistradoOut, status_code=status.HTTP_201_CREATED,
             summary="Registra un cobro manual (mercadopago o transferencia) sobre un presupuesto aceptado",
             responses=_ERRORES_PAGO)
async def registrar_pago(
    paciente_id: int,
    presupuesto_id: int,
    data: PagoCreate,
    contexto: PermissionContext = Depends(require_recepcion_o_admin),
    session: AsyncSession = Depends(get_session),
    ahora: datetime = Depends(get_reloj),
) -> PagoRegistradoOut:
    return await service_pagos.registrar_pago(session, contexto.usuario_id, paciente_id, presupuesto_id, data, ahora)


@router.get(_RUTA_PAGOS, response_model=PagosPresupuestoOut,
            summary="Pagos del presupuesto (registrados y anulados) con total pagado y saldo", responses=_ERRORES_PAGO)
async def listar_pagos(
    paciente_id: int,
    presupuesto_id: int,
    contexto: PermissionContext = Depends(require_recepcion_o_admin),
    session: AsyncSession = Depends(get_session),
) -> PagosPresupuestoOut:
    return await service_pagos.listar_pagos(session, contexto, paciente_id, presupuesto_id)


@router.post(_RUTA_PAGOS + "/{pago_id}/anular", response_model=PagoRegistradoOut,
             summary="Anula un pago registrado con motivo (nunca se borra); el saldo vuelve a sumar su monto",
             responses=_ERRORES_PAGO)
async def anular_pago(
    paciente_id: int,
    presupuesto_id: int,
    pago_id: int,
    cuerpo: AnulacionIn,
    contexto: PermissionContext = Depends(require_recepcion_o_admin),
    session: AsyncSession = Depends(get_session),
    ahora: datetime = Depends(get_reloj),
) -> PagoRegistradoOut:
    return await service_pagos.anular_pago(
        session, contexto.usuario_id, paciente_id, presupuesto_id, pago_id, cuerpo.motivo, ahora)
