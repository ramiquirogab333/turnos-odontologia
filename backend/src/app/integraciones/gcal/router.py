"""Router de Google Calendar del panel (C-10, D9, R15): conexión OAuth, estado, conflictos y su resolución."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import PermissionContext, get_current_user, require_recepcion_o_admin, require_role
from app.gestion.deps import get_reloj
from app.integraciones.gcal import conflictos, oauth
from app.integraciones.gcal.deps import get_proveedor
from app.integraciones.gcal.errores import (AccionNoValidaError, ConexionActivaError, ConexionInexistenteError,
                                            ConflictoCerradoError, ConflictoInexistenteError, GcalNoConfiguradoError,
                                            SinPermisoSobreConexionError)
from app.integraciones.gcal.proveedor import ProveedorCalendario
from app.integraciones.gcal.schemas import ConexionOut, ConflictoOut, EstadoConflicto, IniciarOut, ResolverIn
from app.pacientes.http import respuesta
from app.panel.schemas import ErrorPanelBody
from app.shared.db import get_session
from app.shared.settings import get_settings

router = APIRouter(prefix="/api/panel/google-calendar", tags=["google-calendar"])

_ERRORES = {401: {"description": "Sin token de acceso válido"}}


def _es_recepcion_o_admin(contexto: PermissionContext) -> bool:
    return contexto.tiene_rol("recepcion") or contexto.tiene_rol("admin")


@router.get("/conexiones", response_model=list[ConexionOut],
            summary="Estado de la conexión por profesional (recepción y admin ven todas; la odontóloga, la suya)",
            responses={**_ERRORES, 403: {"description": "Rol sin acceso al panel"}})
async def estado_conexiones(contexto: PermissionContext = Depends(get_current_user),
                            session: AsyncSession = Depends(get_session)) -> list[ConexionOut] | JSONResponse:
    if _es_recepcion_o_admin(contexto):
        return await oauth.listar_conexiones(session, None)
    if contexto.tiene_rol("odontologo"):
        # SinProfesionalAsociadoError (403) lo traduce el handler global
        return await oauth.listar_conexiones(session, await oauth.profesional_del_usuario(session, contexto.usuario_id))
    return respuesta(403, "Rol requerido: recepcion, admin u odontologo", "sin_acceso_al_panel")


@router.post("/conexion/iniciar", response_model=IniciarOut,
             summary="La profesional pide la URL de consentimiento de Google (PKCE + state de un solo uso)",
             responses={**_ERRORES, 403: {"description": "Solo una odontóloga con profesional vinculada"},
                        409: {"model": ErrorPanelBody, "description": "`conexion_activa`"},
                        503: {"model": ErrorPanelBody, "description": "`gcal_no_configurado`"}})
async def iniciar(contexto: PermissionContext = Depends(require_role("odontologo")),
                  session: AsyncSession = Depends(get_session),
                  ahora: datetime = Depends(get_reloj)) -> IniciarOut | JSONResponse:
    try:
        return IniciarOut(url_autorizacion=await oauth.iniciar_conexion(session, contexto.usuario_id, get_settings(), ahora))
    except GcalNoConfiguradoError as exc:
        return respuesta(503, str(exc), "gcal_no_configurado")
    except ConexionActivaError as exc:
        return respuesta(409, str(exc), "conexion_activa")


@router.get("/oauth/callback", status_code=303, response_class=RedirectResponse,
            summary="Regreso de Google: canjea el código y vuelve al panel con el resultado (la autenticidad la da el state)",
            responses={303: {"description": "Redirección a `#/google-calendar?resultado=...`"}})
async def callback(code: str | None = None, state: str | None = None, error: str | None = None,
                   session: AsyncSession = Depends(get_session), proveedor: ProveedorCalendario = Depends(get_proveedor),
                   ahora: datetime = Depends(get_reloj)) -> RedirectResponse:
    ajustes = get_settings()
    resultado = await oauth.completar_callback(session, proveedor, code, state, error, ajustes, ahora)
    return RedirectResponse(f"{ajustes.public_panel_url.rstrip('/')}/#/google-calendar?resultado={resultado}",
                            status_code=303)


@router.delete("/conexiones/{profesional_id}", status_code=204,
               summary="Desconecta: revoca el token, borra los tokens guardados y desvincula los eventos (siguen en Google)",
               responses={**_ERRORES, 403: {"description": "Solo la propia profesional o admin"},
                          404: {"model": ErrorPanelBody, "description": "`conexion_inexistente`"}})
async def desconectar(profesional_id: int, contexto: PermissionContext = Depends(get_current_user),
                      session: AsyncSession = Depends(get_session), proveedor: ProveedorCalendario = Depends(get_proveedor),
                      ahora: datetime = Depends(get_reloj)) -> Response:
    if not (contexto.tiene_rol("admin") or contexto.tiene_rol("odontologo")):
        return respuesta(403, "Solo la propia profesional o un administrador puede desconectar", "conexion_ajena")
    try:
        await oauth.desconectar(session, proveedor, profesional_id, contexto.usuario_id, contexto.roles,
                                get_settings(), ahora)
    except SinPermisoSobreConexionError as exc:
        return respuesta(403, str(exc), "conexion_ajena")
    except ConexionInexistenteError as exc:
        return respuesta(404, str(exc), "conexion_inexistente")
    return Response(status_code=204)


@router.get("/conflictos", response_model=list[ConflictoOut],
            summary="Conflictos con Google Calendar, con el horario del sistema, el de Google y las acciones posibles",
            responses={**_ERRORES, 403: {"description": "Rol sin acceso al panel"}})
async def listar_conflictos(
    estado: Annotated[EstadoConflicto, Query(description="Por defecto, los abiertos")] = "abierto",
    profesional_id: int | None = None,
    contexto: PermissionContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ConflictoOut] | JSONResponse:
    if _es_recepcion_o_admin(contexto):
        return await conflictos.listar(session, estado, profesional_id, puede_resolver=True)
    if contexto.tiene_rol("odontologo"):
        propia = await oauth.profesional_del_usuario(session, contexto.usuario_id)
        if profesional_id not in (None, propia):
            return []  # nunca las de otra profesional
        return await conflictos.listar(session, estado, propia, puede_resolver=False)
    return respuesta(403, "Rol requerido: recepcion, admin u odontologo", "sin_acceso_al_panel")


@router.post("/conflictos/{conflicto_id}/resolver", response_model=ConflictoOut,
             summary="Recepción o admin resuelve un conflicto con una acción válida para su tipo",
             responses={**_ERRORES, 403: {"description": "Solo recepción y admin"},
                        404: {"model": ErrorPanelBody, "description": "`conflicto_inexistente`"},
                        409: {"model": ErrorPanelBody, "description": "`conflicto_cerrado`"},
                        422: {"model": ErrorPanelBody, "description": "`accion_no_valida`"}})
async def resolver(conflicto_id: int, datos: ResolverIn,
                   contexto: PermissionContext = Depends(require_recepcion_o_admin),
                   session: AsyncSession = Depends(get_session),
                   ahora: datetime = Depends(get_reloj)) -> ConflictoOut | JSONResponse:
    try:
        return await conflictos.resolver(session, conflicto_id, datos.accion, contexto.usuario_id, ahora)
    except ConflictoInexistenteError as exc:
        return respuesta(404, str(exc), "conflicto_inexistente")
    except ConflictoCerradoError as exc:
        return respuesta(409, str(exc), "conflicto_cerrado")
    except AccionNoValidaError as exc:
        return respuesta(422, str(exc), "accion_no_valida")
