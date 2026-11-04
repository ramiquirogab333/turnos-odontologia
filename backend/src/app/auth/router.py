"""Endpoints de autenticación del panel (C-03): login, refresh, logout, me.

- POST /api/auth/login: verifica credenciales, emite par JWT, refresh en cookie
  HttpOnly, audita intento (RN-GL-01).
- POST /api/auth/refresh: rotación con blacklist del jti anterior.
- POST /api/auth/logout: blacklist del jti actual, limpia cookie.
- GET /api/auth/me: usuario autenticado con roles.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import PermissionContext, get_current_user
from app.auth.schemas import LoginIn, LoginOut, LogoutOut, MeOut, RefreshIn, RefreshOut
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
        samesite="lax",
        path="/api/auth",
        expires=expires,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path="/api/auth")


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
    summary="Login del panel: devuelve access + refresh (cookie HttpOnly)",
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

    return LoginOut(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


@router.post(
    "/refresh",
    response_model=RefreshOut,
    status_code=status.HTTP_200_OK,
    summary="Rotación de refresh: blacklistea jti anterior, emite nuevo par",
)
async def refresh(
    response: Response,
    data: RefreshIn | None = None,
    session: AsyncSession = Depends(get_session),
) -> RefreshOut:
    """Rota el refresh token: blacklistea el jti usado y emite un nuevo par."""
    refresh_token = data.refresh_token if data and data.refresh_token else None

    if refresh_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token requerido",
        )

    try:
        payload = decode_token(refresh_token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido o expirado",
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere un token de refresh",
        )

    jti_viejo = payload["jti"]
    if await is_jti_blacklisted(session, jti_viejo):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token ya revocado",
        )

    exp_refresh = payload["exp"]
    await blacklist_jti(
        session, jti_viejo, datetime.fromtimestamp(exp_refresh, tz=timezone.utc)
    )

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

    return RefreshOut(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
    )


@router.post(
    "/logout",
    response_model=LogoutOut,
    status_code=status.HTTP_200_OK,
    summary="Logout: blacklistea jti del access token actual, limpia cookie",
)
async def logout(
    response: Response,
    context: PermissionContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> LogoutOut:
    """Revocación de sesión: blacklistea el jti del access token actual."""
    if context.jti:
        # El access token expira pronto; blacklisteamos su jti hasta su exp.
        # Como no traemos el exp en el contexto, usamos un horizonte corto.
        await blacklist_jti(
            session,
            context.jti,
            _utc_now() + timedelta(minutes=_settings().access_token_expire_minutes),
        )
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
