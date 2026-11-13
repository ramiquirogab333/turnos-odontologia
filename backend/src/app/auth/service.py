"""Servicio de autenticación: verificación de contraseña y JWT (R13, R16, R17).

La revocación vive en ``app.auth.sesiones`` (C-15); acá no hay I/O de base de datos.
Los secretos provienen únicamente de variables de entorno a través de Settings.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
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


def _emitir(
    data: dict[str, Any],
    tipo: str,
    por_defecto: timedelta,
    expires_delta: timedelta | None,
    ahora: datetime | None,
    expires_at: datetime | None,
) -> str:
    """Firma un JWT. ``expires_at`` (tope absoluto de la sesión) manda sobre la duración relativa (C-15, D1)."""
    settings = get_settings()
    emitido = ahora or _now()
    vence = expires_at if expires_at is not None else emitido + (expires_delta or por_defecto)
    to_encode = {**data, "exp": vence, "iat": emitido, "type": tipo}
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
    *,
    ahora: datetime | None = None,
    expires_at: datetime | None = None,
) -> str:
    """Crea un JWT de acceso con expiración corta y claims requeridos."""
    return _emitir(data, "access", timedelta(minutes=get_settings().access_token_expire_minutes),
                   expires_delta, ahora, expires_at)


def create_refresh_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
    *,
    ahora: datetime | None = None,
    expires_at: datetime | None = None,
) -> str:
    """Crea un JWT de refresh con expiración mayor (cookie HttpOnly)."""
    return _emitir(data, "refresh", timedelta(minutes=get_settings().refresh_token_expire_minutes),
                   expires_delta, ahora, expires_at)


def decode_token(token: str) -> dict[str, Any]:
    """Decodifica y valida un JWT: firma, expiración y claims requeridos.

    Claims requeridos: sub, roles, email, jti, sid, type, iat, exp (C-15: ``sid`` liga el token a su sesión).
    """
    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "iat"]},
    )
    required = {"sub", "roles", "email", "jti", "sid", "type", "iat", "exp"}
    missing = required - set(payload.keys())
    if missing:
        raise jwt.InvalidTokenError(f"claims faltantes: {sorted(missing)}")
    return payload
