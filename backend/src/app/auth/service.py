"""Servicio de autenticación: verificación de contraseña, JWT y blacklist (R13, R16, R17).

Todo el trabajo de I/O (blacklist de jti) es asíncrono; nunca se bloquea el loop.
Los secretos provienen únicamente de variables de entorno a través de Settings.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import TokenBlacklist
from app.shared.settings import get_settings


def verify_password(plain: str, hashed: str) -> bool:
    """Comprueba que `plain` coincide con `hashed` (bcrypt)."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def hash_password(plain: str) -> str:
    """Genera hash bcrypt de una contraseña en texto plano."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(
    data: dict[str, Any], expires_delta: timedelta | None = None
) -> str:
    """Crea un JWT de acceso con expiración corta y claims requeridos."""
    settings = get_settings()
    to_encode = data.copy()
    expire = _now() + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    to_encode.update(
        {
            "exp": expire,
            "iat": _now(),
            "type": "access",
        }
    )
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(
    data: dict[str, Any], expires_delta: timedelta | None = None
) -> str:
    """Crea un JWT de refresh con expiración mayor (cookie HttpOnly)."""
    settings = get_settings()
    to_encode = data.copy()
    expire = _now() + (
        expires_delta or timedelta(minutes=settings.refresh_token_expire_minutes)
    )
    to_encode.update(
        {
            "exp": expire,
            "iat": _now(),
            "type": "refresh",
        }
    )
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    """Decodifica y valida un JWT: firma, expiración y claims requeridos.

    Claims requeridos: sub, roles, email, jti, type, iat, exp.
    """
    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "iat"]},
    )
    required = {"sub", "roles", "email", "jti", "type", "iat", "exp"}
    missing = required - set(payload.keys())
    if missing:
        raise jwt.InvalidTokenError(f"claims faltantes: {sorted(missing)}")
    return payload


async def is_jti_blacklisted(session: AsyncSession, jti: str) -> bool:
    """True si el jti está en la blacklist y no ha expirado."""
    now = _now()
    result = await session.execute(
        select(TokenBlacklist.id).where(
            TokenBlacklist.jti == jti,
            TokenBlacklist.expires_at > now,
        )
    )
    return result.first() is not None


async def blacklist_jti(
    session: AsyncSession, jti: str, expires_at: datetime
) -> TokenBlacklist:
    """Añade un jti a la blacklist con su expiración."""
    entry = TokenBlacklist(jti=jti, expires_at=expires_at)
    session.add(entry)
    await session.flush()
    return entry
