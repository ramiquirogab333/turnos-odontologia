"""Endpoints de autenticación del panel (C-03, C-08 D10, C-15): login, refresh, logout, me.

Sobre una sesión del servidor (``sesion_panel``): el login la crea, el refresh rota su único ``refresh_jti`` por
compare-and-swap y el logout la revoca. Access y refresh llevan el ``sid`` y cada pedido autenticado verifica la sesión.

- POST /api/auth/login: verifica credenciales (bcrypt en un hilo, hash ficticio si el usuario no existe), devuelve el
  access en el JSON y el refresh SOLO en una cookie HttpOnly/Secure/SameSite=Strict, y audita con la IP real (RN-GL-01).
- POST /api/auth/refresh: lee el refresh únicamente de la cookie y exige ``X-Panel-Csrf: 1``; una sola renovación
  concurrente gana, la otra recibe 401 (nunca 500). Los roles se releen de la base.
- POST /api/auth/logout: revoca la sesión del access y la de la cookie (idempotente) y borra la cookie.
- GET /api/auth/me: usuario autenticado con roles.
"""

from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import PermissionContext, get_current_user
from app.auth.schemas import LoginIn, LoginOut, LogoutOut, MeOut, RefreshOut
from app.auth.service import decode_token, hash_password, verify_password
from app.auth.sesiones import (
    MOTIVO_LOGOUT,
    cargar_contexto,
    crear_sesion,
    emitir_tokens,
    revocar_sesiones,
    rotar_refresh,
)
from app.models.core import RegistroAuditoria, Rol, Usuario, UsuarioRol
from app.shared.db import get_session
from app.shared.limites import (
    RESPUESTA_429_OPENAPI,
    LimiteSuperadoError,
    LimitadorSolicitudes,
    clave_email,
    clave_ip,
    get_limitador,
)
from app.shared.red import ip_cliente
from app.shared.reloj import get_reloj
from app.shared.settings import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/api/auth"
CSRF_HEADER = "X-Panel-Csrf"

_HASH_FICTICIO: list[str] = []


def _settings():
    return get_settings()


async def _hash_ficticio() -> str:
    """Hash bcrypt de una contraseña inventada, una vez por proceso y con el costo de los reales (D4, O14)."""
    if not _HASH_FICTICIO:
        _HASH_FICTICIO.append(await run_in_threadpool(hash_password, uuid4().hex))
    return _HASH_FICTICIO[0]


def _set_refresh_cookie(response: Response, token: str, expires: datetime) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=True,
        samesite="strict",
        path=REFRESH_COOKIE_PATH,
        expires=expires,
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Borra la cookie repitiendo los mismos atributos con los que se emitió."""
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH, httponly=True, secure=True, samesite="strict"
    )


def _no_autenticado(detalle: str) -> JSONResponse:
    """401 que además borra la cookie de refresh (inválida, vencida, revocada o ausente)."""
    respuesta = JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": detalle})
    _clear_refresh_cookie(respuesta)
    return respuesta


async def _audit(
    session: AsyncSession,
    accion: str,
    entidad: str,
    entidad_id: str | None,
    usuario_id: int | None,
    ip: str | None,
    datos_despues: dict[str, str] | None = None,
) -> None:
    session.add(
        RegistroAuditoria(
            usuario_id=usuario_id,
            accion=accion,
            entidad=entidad,
            entidad_id=entidad_id,
            datos_despues=datos_despues,
            ip=ip,
        )
    )


async def _get_user_with_roles(
    session: AsyncSession, email: str
) -> tuple[Usuario, list[str]] | None:
    result = await session.execute(select(Usuario).where(Usuario.email == email))
    usuario = result.scalar_one_or_none()
    if usuario is None:
        return None
    result = await session.execute(
        select(Rol.nombre)
        .join(UsuarioRol, UsuarioRol.rol_id == Rol.id)
        .where(UsuarioRol.usuario_id == usuario.id)
    )
    roles = [row[0] for row in result.all()]
    return usuario, roles


@router.post(
    "/login",
    response_model=LoginOut,
    status_code=status.HTTP_200_OK,
    summary="Login del panel: access en el JSON, refresh en cookie HttpOnly",
    responses=RESPUESTA_429_OPENAPI,
)
async def login(
    request: Request,
    response: Response,
    data: LoginIn,
    session: AsyncSession = Depends(get_session),
    ahora: datetime = Depends(get_reloj),
    limitador: LimitadorSolicitudes = Depends(get_limitador),
) -> LoginOut:
    """Autentica al usuario, abre una sesión del servidor y emite el par de tokens JWT."""
    email = data.email.strip().lower()
    ip = ip_cliente(request)
    ajustes = _settings()
    llave_ip = f"rl:v1:login:ip:{clave_ip(request)}"
    llave_par = f"rl:v1:login:ipemail:{clave_ip(request)}:{clave_email(email)}"
    llave_email = f"rl:v1:login:email:{clave_email(email)}"
    # Antes de verificar la contraseña: las claves de fallos solo se consultan; la de IP cuenta cada intento (O6).
    bloqueos = (
        ("ipemail", await limitador.consultar(llave_par, ajustes.rate_limit_login_ip_email_max)),
        ("email", await limitador.consultar(llave_email, ajustes.rate_limit_login_email_max)),
        ("ip", await limitador.consumir(llave_ip, ajustes.rate_limit_login_ip_max,
                                        ajustes.rate_limit_login_ip_ventana_seg)),
    )
    bloqueado = [(nombre, r) for nombre, r in bloqueos if not r.permitido]
    if bloqueado:
        for nombre, r in bloqueado:
            if r.recien_bloqueado:  # una sola vez por clave y ventana: el ataque no inunda la auditoría (O15)
                await _audit(session, "LOGIN_BLOQUEADO", "usuario", None, None, ip, {"limite": nombre})
        await session.commit()
        raise LimiteSuperadoError(max(r.reintentar_en_segundos for _, r in bloqueado))
    encontrado = await _get_user_with_roles(session, email)
    # Siempre se corre una verificación bcrypt (fuera del loop, R16): sin usuario, contra un hash ficticio.
    hash_real = encontrado[0].hashed_password if encontrado is not None else await _hash_ficticio()
    correcta = await run_in_threadpool(verify_password, data.password, hash_real)

    if encontrado is None or not correcta:
        await limitador.registrar(llave_par, ajustes.rate_limit_login_ip_email_ventana_seg)
        await limitador.registrar(llave_email, ajustes.rate_limit_login_email_ventana_seg)
        await _audit(session, "LOGIN_FAILED", "usuario", email if encontrado is None else str(encontrado[0].id),
                     None if encontrado is None else int(encontrado[0].id), ip, {"motivo": "credenciales"})
        await session.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")
    usuario, roles = encontrado
    if not usuario.is_active:
        await limitador.registrar(llave_par, ajustes.rate_limit_login_ip_email_ventana_seg)
        await limitador.registrar(llave_email, ajustes.rate_limit_login_email_ventana_seg)
        # Misma respuesta que unas credenciales erróneas: no revela que la cuenta existe y está desactivada.
        await _audit(session, "LOGIN_FAILED", "usuario", str(usuario.id), int(usuario.id), ip,
                     {"motivo": "usuario_inactivo"})
        await session.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")

    await limitador.reiniciar(llave_par)  # el éxito reinicia el par IP + email
    nueva = await crear_sesion(session, usuario_id=int(usuario.id), ahora=ahora,
                               maximo_horas=ajustes.sesion_maxima_horas, ip=ip)
    tokens = emitir_tokens(
        sid=nueva.sid, usuario_id=int(usuario.id), email=usuario.email, roles=roles, ahora=ahora,
        expira_en=nueva.expira_en, access_minutos=ajustes.access_token_expire_minutes,
        refresh_minutos=ajustes.refresh_token_expire_minutes, refresh_jti=nueva.refresh_jti)
    _set_refresh_cookie(response, tokens.refresh_token, tokens.refresh_expira_en)
    await _audit(session, "LOGIN_OK", "usuario", str(usuario.id), int(usuario.id), ip)
    await session.commit()
    return LoginOut(access_token=tokens.access_token, token_type="bearer")


@router.post(
    "/refresh",
    response_model=RefreshOut,
    status_code=status.HTTP_200_OK,
    summary="Rotación de refresh (solo cookie + X-Panel-Csrf): compare-and-swap sobre la sesión, access nuevo",
    responses={
        **RESPUESTA_429_OPENAPI,
        401: {"description": "Cookie ausente, inválida, vencida, sesión revocada o ya rotada (la cookie se borra)"},
        403: {"description": "Falta la cabecera anti-CSRF `X-Panel-Csrf: 1` (motivo `csrf_requerido`)"},
    },
)
async def refresh(
    request: Request,
    response: Response,
    x_panel_csrf: str | None = Header(default=None, alias=CSRF_HEADER),
    session: AsyncSession = Depends(get_session),
    ahora: datetime = Depends(get_reloj),
    limitador: LimitadorSolicitudes = Depends(get_limitador),
) -> RefreshOut | JSONResponse:
    """Rota el refresh de la cookie: una sola renovación gana; emite access y refresh nuevos con roles de la base."""
    # El límite cuenta ANTES de validar la cabecera CSRF: un atacante sin cabecera también consume (O7).
    ajustes_limite = _settings()
    cupo = await limitador.consumir(f"rl:v1:refresh:ip:{clave_ip(request)}", ajustes_limite.rate_limit_refresh_ip_max,
                                    ajustes_limite.rate_limit_refresh_ip_ventana_seg)
    if not cupo.permitido:
        raise LimiteSuperadoError(cupo.reintentar_en_segundos)
    # La cabecera se valida ANTES de leer la cookie: un sitio ajeno no puede enviarla (preflight sin CORS).
    if x_panel_csrf != "1":
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Falta la cabecera de protección del panel", "motivo": "csrf_requerido"},
        )
    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not refresh_token:
        return _no_autenticado("Refresh token requerido")
    try:
        payload = decode_token(refresh_token)
    except Exception:
        return _no_autenticado("Refresh token inválido o expirado")
    if payload.get("type") != "refresh":
        return _no_autenticado("Se requiere un token de refresh")

    nuevo_jti = uuid4()
    rotada = await rotar_refresh(session, sid=payload["sid"], jti_presentado=payload["jti"], nuevo_jti=nuevo_jti,
                                 ahora=ahora)
    if rotada is None:
        await session.rollback()
        return _no_autenticado("Sesión inválida o vencida")
    usuario_id, expira_en = rotada
    contexto = await cargar_contexto(session, sid=payload["sid"], usuario_id=usuario_id)
    if contexto is None or not contexto.activo or str(usuario_id) != str(payload["sub"]):
        await session.rollback()
        return _no_autenticado("Sesión inválida o vencida")

    ajustes = _settings()
    tokens = emitir_tokens(
        sid=payload["sid"], usuario_id=usuario_id, email=contexto.email, roles=contexto.roles, ahora=ahora,
        expira_en=expira_en, access_minutos=ajustes.access_token_expire_minutes,
        refresh_minutos=ajustes.refresh_token_expire_minutes, refresh_jti=nuevo_jti)
    _set_refresh_cookie(response, tokens.refresh_token, tokens.refresh_expira_en)
    await session.commit()
    return RefreshOut(access_token=tokens.access_token, token_type="bearer")


@router.post(
    "/logout",
    response_model=LogoutOut,
    status_code=status.HTTP_200_OK,
    summary="Logout: revoca la sesión del access y la de la cookie; limpia la cookie",
)
async def logout(
    request: Request,
    response: Response,
    context: PermissionContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    ahora: datetime = Depends(get_reloj),
) -> LogoutOut:
    """Revoca la sesión. Idempotente: repetir el logout nunca produce un error interno.

    Revoca la sesión del access y, si decodifica, la de la cookie (otra pestaña pudo haber abierto otra).
    """
    sids: list[object] = [context.sid]
    cookie = request.cookies.get(REFRESH_COOKIE_NAME)
    if cookie:
        try:
            payload = decode_token(cookie)
            if payload.get("type") == "refresh":
                sids.append(payload["sid"])
        except Exception:  # noqa: BLE001 - una cookie ilegible no impide cerrar la sesión
            pass
    await revocar_sesiones(session, sids, motivo=MOTIVO_LOGOUT, ahora=ahora)
    _clear_refresh_cookie(response)
    await _audit(session, "LOGOUT", "usuario", str(context.usuario_id), context.usuario_id, ip_cliente(request))
    await session.commit()
    return LogoutOut(detalle="sesión revocada")


@router.get(
    "/me",
    response_model=MeOut,
    status_code=status.HTTP_200_OK,
    summary="Usuario autenticado con sus roles",
)
async def me(
    context: PermissionContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MeOut:
    """Devuelve el usuario autenticado y sus roles (leídos de la base en este pedido)."""
    result = await session.execute(select(Usuario).where(Usuario.id == context.usuario_id))
    usuario = result.scalar_one_or_none()
    nombre_completo = usuario.nombre_completo if usuario else ""
    return MeOut(
        id=context.usuario_id,
        email=context.email,
        nombre_completo=nombre_completo,
        roles=context.roles,
    )
