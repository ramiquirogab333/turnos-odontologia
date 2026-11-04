"""Autorización RBAC: PermissionContext y dependencia require_role (C-03).

Matriz RBAC (03_actores_y_roles.md):
- odontólogo: lectura de su agenda y sus pacientes.
- recepcion / admin: CRUD total sobre turnos, pacientes, disponibilidad, caja.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.service import decode_token

bearer_scheme = HTTPBearer(auto_error=False)


class PermissionContext:
    """Contexto de permisos del usuario autenticado en la petición actual."""

    def __init__(
        self,
        usuario_id: int,
        email: str,
        roles: list[str],
        jti: str | None = None,
    ) -> None:
        self.usuario_id = usuario_id
        self.email = email
        self.roles = list(roles)
        self.jti = jti

    def tiene_rol(self, rol: str) -> bool:
        """True si el usuario posee el rol dado."""
        return rol in self.roles

    def require_role(self, rol_requerido: str) -> "PermissionContext":
        """Devuelve el contexto si tiene el rol; lanza 403 en caso contrario."""
        if not self.tiene_rol(rol_requerido):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Rol requerido: {rol_requerido}",
            )
        return self


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> PermissionContext:
    """Dependencia FastAPI: decodifica el access token y retorna PermissionContext."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de acceso requerido",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(credentials.credentials)
    except Exception:  # token inválido / expirado -> 401
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere un token de acceso",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return PermissionContext(
        usuario_id=int(payload["sub"]),
        email=str(payload["email"]),
        roles=list(payload.get("roles", [])),
        jti=str(payload.get("jti", "")),
    )


def require_role(rol_requerido: str):
    """Dependencia parametrizable: inyecta PermissionContext y exige un rol."""

    async def _dependency(context: PermissionContext = Depends(get_current_user)):
        return context.require_role(rol_requerido)

    return _dependency
