"""Endpoints de autenticación del panel (C-03, endurecidos en C-08 / D10): login, refresh, logout, me.

- POST /api/auth/login: verifica credenciales, devuelve el access en el JSON y el refresh SOLO en una cookie
  HttpOnly/Secure/SameSite=Strict (nunca en el cuerpo), audita el intento (RN-GL-01).
- POST /api/auth/refresh: lee el refresh únicamente de la cookie y exige la cabecera ``X-Panel-Csrf: 1``
  (defensa CSRF junto con SameSite=Strict); rota blacklisteando el jti anterior. La rotación concurrente tiene
  un solo ganador: el perdedor recibe 401, nunca 500. Si el API se publica con CORS hay que revisar esta defensa.
- POST /api/auth/logout: revoca el jti del access y el del refresh de la cookie hasta que el refresh pueda vencer
  (idempotente) y borra la cookie.
- GET /api/auth/me: usuario autenticado con roles.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import PermissionContext, get_current_user
from app.auth.schemas import LoginIn, LoginOut, LogoutOut, MeOut, RefreshOut
from app.auth.service import (
    blacklist_jti,
    create_access_token,
    create_refresh_token,
    decode_token,
    is_jti_blacklisted,
    verify_password,
)
from app.models.auth import TokenBlacklist
from app.models.core import RegistroAuditoria, Rol, Usuario, UsuarioRol
from app.shared.db import get_session
from app.shared.settings import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/api/auth"
CSRF_HEADER = "X-Panel-Csrf"


def _settings():
    return get_settings()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


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
) -> None:
    session.add(
        RegistroAuditoria(
            usuario_id=usuario_id,
            accion=accion,
            entidad=entidad,
            entidad_id=entidad_id,
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
)
async def login(
    response: Response,
    data: LoginIn,
    session: AsyncSession = Depends(get_session),
) -> LoginOut:
    """Autentica al usuario y emite par de tokens JWT."""
    encontrado = await _get_user_with_roles(session, data.email)
    ip = "testclient"

    if encontrado is None:
        await _audit(session, "LOGIN_FAILED", "usuario", data.email, None, ip)
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
        )
    usuario, roles = encontrado
    if not verify_password(data.password, usuario.hashed_password):
        await _audit(session, "LOGIN_FAILED", "usuario", str(usuario.id), int(usuario.id), ip)
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
        )

    token_data = {
        "sub": str(usuario.id),
        "roles": roles,
        "email": usuario.email,
        "jti": str(uuid4()),
    }
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    refresh_expires = _utc_now() + timedelta(
        minutes=_settings().refresh_token_expire_minutes
    )
    _set_refresh_cookie(response, refresh_token, refresh_expires)

    await _audit(session, "LOGIN_OK", "usuario", str(usuario.id), int(usuario.id), ip)
    await session.commit()

    return LoginOut(access_token=access_token, token_type="bearer")


@router.post(
    "/refresh",
    response_model=RefreshOut,
    status_code=status.HTTP_200_OK,
    summary="Rotación de refresh (solo cookie + X-Panel-Csrf): blacklistea el jti anterior, emite access nuevo",
    responses={
        401: {"description": "Cookie ausente, inválida, vencida, revocada o ya rotada (la cookie se borra)"},
        403: {"description": "Falta la cabecera anti-CSRF `X-Panel-Csrf: 1` (motivo `csrf_requerido`)"},
    },
)
async def refresh(
    request: Request,
    response: Response,
    x_panel_csrf: str | None = Header(default=None, alias=CSRF_HEADER),
    session: AsyncSession = Depends(get_session),
) -> RefreshOut | JSONResponse:
    """Rota el refresh de la cookie: blacklistea el jti usado y emite un access nuevo con un refresh nuevo en cookie."""
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

    jti_viejo = payload["jti"]
    if await is_jti_blacklisted(session, jti_viejo):
        return _no_autenticado("Refresh token ya revocado")

    # Una sola rotación gana: si otra petición ya revocó este jti (o lo revoca a la vez), esta pierde con 401.
    exp_refresh = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    if not await blacklist_jti(session, jti_viejo, exp_refresh):
        await session.rollback()
        return _no_autenticado("Refresh token ya revocado")

    token_data = {
        "sub": payload["sub"],
        "roles": payload.get("roles", []),
        "email": payload["email"],
        "jti": str(uuid4()),
    }
    access_token = create_access_token(token_data)
    new_refresh_token = create_refresh_token(token_data)

    refresh_expires = _utc_now() + timedelta(
        minutes=_settings().refresh_token_expire_minutes
    )
    _set_refresh_cookie(response, new_refresh_token, refresh_expires)

    await session.commit()

    return RefreshOut(access_token=access_token, token_type="bearer")


@router.post(
    "/logout",
    response_model=LogoutOut,
    status_code=status.HTTP_200_OK,
    summary="Logout: revoca el access y el refresh de la cookie hasta que el refresh pueda vencer; limpia la cookie",
)
async def logout(
    request: Request,
    response: Response,
    context: PermissionContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> LogoutOut:
    """Revoca la sesión. Idempotente: repetir el logout nunca produce un error interno.

    Revoca el jti del access y, si decodifica, el del refresh de la cookie (puede ser otro: otra pestaña pudo
    rotarlo). Ambos hasta ``ahora + refresh_token_expire_minutes``: antes el horizonte era el del access (15 min)
    y el refresh de 7 días dejaba de estar revocado.
    """
    horizonte = _utc_now() + timedelta(minutes=_settings().refresh_token_expire_minutes)
    jtis = {context.jti} if context.jti else set()
    cookie = request.cookies.get(REFRESH_COOKIE_NAME)
    if cookie:
        try:
            payload = decode_token(cookie)
            if payload.get("type") == "refresh":
                jtis.add(str(payload["jti"]))
        except Exception:  # noqa: BLE001 - una cookie ilegible no impide cerrar la sesión
            pass
    for jti in sorted(jtis):
        await blacklist_jti(session, jti, horizonte)
    _clear_refresh_cookie(response)
    await _audit(
        session,
        "LOGOUT",
        "usuario",
        str(context.usuario_id),
        context.usuario_id,
        "testclient",
    )
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
    """Devuelve el usuario autenticado y sus roles."""
    result = await session.execute(select(Usuario).where(Usuario.id == context.usuario_id))
    usuario = result.scalar_one_or_none()
    nombre_completo = usuario.nombre_completo if usuario else ""
    return MeOut(
        id=context.usuario_id,
        email=context.email,
        nombre_completo=nombre_completo,
        roles=context.roles,
    )
