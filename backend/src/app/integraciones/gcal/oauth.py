"""Conexión OAuth con Google Calendar (C-10, D3, O1-O3, O14): iniciar, callback, desconectar y estado.

Es el único lugar de la API que habla con Google: el canje del código del callback (``await`` con ``httpx``, timeout
10 s), respuesta a una acción explícita de la usuaria y no a una transición de turno (R16). El ``state`` es un JWT de un
solo uso (el nonce se guarda hasheado en la conexión) con PKCE; ningún token sale en una respuesta, log ni auditoría.
"""

import base64
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import jwt
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.integraciones.gcal.cifrado import TokenIlegible, cifrar, descifrar
from app.integraciones.gcal.errores import (ConexionActivaError, ConexionInexistenteError, GcalNoConfiguradoError,
                                            SinPermisoSobreConexionError)
from app.integraciones.gcal.models import EventoCalendar, GcalConexion, GcalConflicto
from app.integraciones.gcal.proveedor import ErrorProveedor, ProveedorCalendario
from app.integraciones.gcal.schemas import ConexionOut
from app.models.core import RegistroAuditoria, Usuario
from app.panel.service import SinProfesionalAsociadoError
from app.shared.logger import get_logger
from app.shared.settings import Settings
from app.turnos.models import Profesional

logger = get_logger(__name__)

SCOPE = "https://www.googleapis.com/auth/calendar.events openid email"
VIGENCIA_STATE = timedelta(minutes=10)
TIPO_STATE = "gcal_state"
INDICACION_REVOCADA = "Volvé a conectar Google Calendar"


def _clave(ajustes: Settings) -> str:
    if not ajustes.gcal_configurado or ajustes.gcal_token_clave is None:
        raise GcalNoConfiguradoError()
    return ajustes.gcal_token_clave.get_secret_value()


def _hash_nonce(nonce: str) -> str:
    return hashlib.sha256(nonce.encode()).hexdigest()


def crear_state(profesional_id: int, nonce: str, ajustes: Settings, ahora: datetime) -> str:
    """JWT HS256 firmado con la clave del backend: tipo, profesional, nonce y vencimiento a 10 minutos."""
    carga = {"type": TIPO_STATE, "profesional_id": profesional_id, "nonce": nonce,
             "exp": int((ahora + VIGENCIA_STATE).timestamp())}
    return jwt.encode(carga, ajustes.jwt_secret_key, algorithm=ajustes.jwt_algorithm)


def leer_state(state: str, ajustes: Settings, ahora: datetime) -> dict[str, Any] | None:
    """Devuelve la carga si la firma, el tipo y el vencimiento son válidos; ``None`` en cualquier otro caso."""
    try:
        carga = jwt.decode(state, ajustes.jwt_secret_key, algorithms=[ajustes.jwt_algorithm],
                           options={"verify_exp": False})
    except jwt.PyJWTError:
        return None
    if carga.get("type") != TIPO_STATE or not isinstance(carga.get("exp"), int) or carga["exp"] <= ahora.timestamp():
        return None
    if not isinstance(carga.get("profesional_id"), int) or not isinstance(carga.get("nonce"), str):
        return None
    return carga


def _auditar(session: AsyncSession, usuario_id: int | None, accion: str, conexion: GcalConexion,
             despues: dict[str, object]) -> None:
    session.add(RegistroAuditoria(  # RN-GL-01: sin tokens ni datos del paciente
        usuario_id=usuario_id, accion=accion, entidad="gcal_conexion", entidad_id=str(conexion.id),
        datos_despues={"profesional_id": conexion.profesional_id, **despues}, ip=None))


async def _profesional_de(session: AsyncSession, usuario_id: int) -> int:
    profesional_id = (await session.execute(select(Usuario.profesional_id).where(Usuario.id == usuario_id))
                      ).scalar_one_or_none()
    if profesional_id is None:
        raise SinProfesionalAsociadoError()
    return int(profesional_id)


# --- iniciar ---------------------------------------------------------------------------------------------------

async def iniciar_conexion(session: AsyncSession, usuario_id: int, ajustes: Settings, ahora: datetime) -> str:
    """Deja la conexión ``pendiente`` y devuelve la URL de consentimiento de Google (PKCE + ``state``)."""
    clave = _clave(ajustes)
    profesional_id = await _profesional_de(session, usuario_id)
    conexion = (await session.execute(select(GcalConexion).where(GcalConexion.profesional_id == profesional_id)
                                      .with_for_update())).scalar_one_or_none()
    if conexion is not None and conexion.estado == "activa":
        await session.rollback()
        raise ConexionActivaError()
    nonce, verificador = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    if conexion is None:
        conexion = GcalConexion(profesional_id=profesional_id, estado="pendiente")
        session.add(conexion)
    conexion.estado, conexion.usuario_id = "pendiente", usuario_id
    conexion.oauth_nonce_hash = _hash_nonce(nonce)
    conexion.oauth_verifier_cifrado = cifrar(verificador, clave)
    conexion.oauth_expira_en = ahora + VIGENCIA_STATE
    await session.commit()
    desafio = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).decode().rstrip("=")
    parametros = {
        "client_id": ajustes.gcal_client_id or "", "redirect_uri": ajustes.gcal_redirect_uri, "response_type": "code",
        "scope": SCOPE, "access_type": "offline", "prompt": "consent",
        "state": crear_state(profesional_id, nonce, ajustes, ahora), "code_challenge": desafio,
        "code_challenge_method": "S256"}
    return f"{ajustes.gcal_oauth_base_url.rstrip('/')}/o/oauth2/v2/auth?{urlencode(parametros)}"


# --- callback --------------------------------------------------------------------------------------------------

async def completar_callback(session: AsyncSession, proveedor: ProveedorCalendario, codigo: str | None,
                             state: str | None, error: str | None, ajustes: Settings, ahora: datetime) -> str:
    """Valida el ``state``, canjea el código y activa la conexión. Devuelve el ``resultado`` para el panel."""
    carga = leer_state(state, ajustes, ahora) if state else None
    if carga is None or not ajustes.gcal_configurado:
        return "error_autorizacion"
    clave = _clave(ajustes)
    conexion = (await session.execute(select(GcalConexion).where(GcalConexion.profesional_id == carga["profesional_id"])
                                      .with_for_update())).scalar_one_or_none()
    if (conexion is None or conexion.estado != "pendiente" or conexion.oauth_nonce_hash != _hash_nonce(carga["nonce"])
            or conexion.oauth_expira_en is None or conexion.oauth_expira_en <= ahora):
        await session.rollback()
        return "error_autorizacion"
    verificador_cifrado = conexion.oauth_verifier_cifrado
    # El state se consume ya (un solo uso): si el canje falla, la conexión queda desconectada y se reintenta desde cero.
    conexion.estado = "desconectada"
    conexion.oauth_nonce_hash = conexion.oauth_verifier_cifrado = conexion.oauth_expira_en = None
    conexion.refresh_token_cifrado = conexion.access_token_cifrado = conexion.access_expira_en = None
    await session.commit()
    if error is not None:
        return "permiso_denegado" if error == "access_denied" else "error_autorizacion"
    if not codigo or verificador_cifrado is None:
        return "error_autorizacion"
    try:
        tokens = await proveedor.canjear_codigo(codigo, descifrar(verificador_cifrado, clave), ajustes.gcal_redirect_uri)
        if tokens.refresh_token is None:
            return "error_autorizacion"
    except (ErrorProveedor, TokenIlegible) as fallo:
        logger.warning("gcal: canje de autorización fallido (%s)", type(fallo).__name__)
        return "error_autorizacion"
    conexion.estado, conexion.cuenta_email, conexion.conectada_en = "activa", tokens.email, ahora
    conexion.refresh_token_cifrado = cifrar(tokens.refresh_token, clave)
    conexion.access_token_cifrado = cifrar(tokens.access_token, clave)
    conexion.access_expira_en = tokens.expira_en
    conexion.sync_token, conexion.proximo_intento_en = None, None
    conexion.fallos_consecutivos, conexion.ultimo_error = 0, None
    _auditar(session, conexion.usuario_id, "UPDATE", conexion, {"estado": "activa", "origen": "oauth_callback"})
    await session.commit()
    return "conectado"


# --- desconectar -----------------------------------------------------------------------------------------------

async def desconectar(session: AsyncSession, proveedor: ProveedorCalendario, profesional_id: int, usuario_id: int,
                      roles: list[str], ajustes: Settings, ahora: datetime) -> None:
    """Revoca el token (si se puede), borra los tokens y deja eventos desvinculados y conflictos cerrados (O14)."""
    if "admin" not in roles and await _profesional_de(session, usuario_id) != profesional_id:
        raise SinPermisoSobreConexionError()
    conexion = (await session.execute(select(GcalConexion).where(GcalConexion.profesional_id == profesional_id)
                                      .with_for_update())).scalar_one_or_none()
    if conexion is None:
        await session.rollback()
        raise ConexionInexistenteError()
    if conexion.refresh_token_cifrado and ajustes.gcal_token_clave is not None:
        try:
            await proveedor.revocar(descifrar(conexion.refresh_token_cifrado, ajustes.gcal_token_clave.get_secret_value()))
        except (ErrorProveedor, TokenIlegible) as fallo:  # la desconexión local no depende de Google
            logger.warning("gcal: no se pudo revocar el token en Google (%s)", type(fallo).__name__)
    anterior = conexion.estado
    conexion.estado = "desconectada"
    conexion.refresh_token_cifrado = conexion.access_token_cifrado = conexion.access_expira_en = None
    conexion.sync_token = conexion.oauth_nonce_hash = conexion.oauth_verifier_cifrado = None
    conexion.oauth_expira_en = conexion.proximo_intento_en = None
    await session.execute(update(EventoCalendar).where(
        EventoCalendar.conexion_id == conexion.id, EventoCalendar.origen == "sistema",
        EventoCalendar.estado.in_(("pendiente", "sincronizado"))).values(estado="desvinculado"))
    await session.execute(update(EventoCalendar).where(
        EventoCalendar.conexion_id == conexion.id, EventoCalendar.origen == "google").values(
        ocupa=False, estado="borrado"))
    await session.execute(update(GcalConflicto).where(
        GcalConflicto.conexion_id == conexion.id, GcalConflicto.estado == "abierto").values(
        estado="resuelto", resolucion="revisado", resuelto_por_usuario_id=usuario_id, resuelto_en=ahora))
    _auditar(session, usuario_id, "UPDATE", conexion, {"estado": "desconectada", "antes": anterior})
    await session.commit()


# --- estado ----------------------------------------------------------------------------------------------------

async def listar_conexiones(session: AsyncSession, profesional_id: int | None) -> list[ConexionOut]:
    """Una fila por profesional (``sin_conectar`` si no hay conexión); ``profesional_id`` acota a una sola."""
    abiertos = (select(GcalConflicto.conexion_id.label("cid"), func.count().label("n"))
                .where(GcalConflicto.estado == "abierto").group_by(GcalConflicto.conexion_id).subquery())
    consulta = (select(Profesional.id, Profesional.nombre, GcalConexion.estado, GcalConexion.cuenta_email,
                       GcalConexion.ultimo_sync_ok_en, func.coalesce(abiertos.c.n, 0))
                .outerjoin(GcalConexion, GcalConexion.profesional_id == Profesional.id)
                .outerjoin(abiertos, abiertos.c.cid == GcalConexion.id)
                .order_by(Profesional.nombre, Profesional.id))
    if profesional_id is not None:
        consulta = consulta.where(Profesional.id == profesional_id)
    salida: list[ConexionOut] = []
    for pid, nombre, estado, email, ultima, n in (await session.execute(consulta)).all():
        salida.append(ConexionOut(
            profesional_id=int(pid), profesional_nombre=nombre, estado=estado or "sin_conectar",
            cuenta_email=email, ultima_sync_ok_en=ultima, conflictos_abiertos=int(n),
            indicacion=INDICACION_REVOCADA if estado == "revocada" else None))
    return salida


async def profesional_del_usuario(session: AsyncSession, usuario_id: int) -> int:
    """Profesional vinculada al usuario (``SinProfesionalAsociadoError`` si no hay)."""
    return await _profesional_de(session, usuario_id)
