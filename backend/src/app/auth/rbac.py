"""Autorización RBAC: PermissionContext y dependencia require_role (C-03).

Matriz RBAC (03_actores_y_roles.md):
- odontólogo: lectura de su agenda y sus pacientes.
- recepcion / admin: CRUD total sobre turnos, pacientes, disponibilidad, caja.
"""

from datetime import datetime

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.sesiones import cargar_contexto, sesion_vigente
from app.auth.service import decode_token
from app.plataforma.auditoria import contexto_auditoria
from app.shared.db import get_session
from app.shared.red import ip_cliente
from app.shared.reloj import get_reloj

bearer_scheme = HTTPBearer(auto_error=False)


class PermissionContext:
    """Contexto de permisos del usuario autenticado en la petición actual."""

    def __init__(
        self,
        usuario_id: int,
        email: str,
        roles: list[str],
        jti: str | None = None,
        sid: str | None = None,
    ) -> None:
        self.usuario_id = usuario_id
        self.email = email
        self.roles = list(roles)
        self.jti = jti
        self.sid = sid

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


def _sesion_invalida() -> HTTPException:
    """401 genérico: no distingue sesión cerrada, vencida ni usuario inactivo."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sesión inválida o vencida",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
    ahora: datetime = Depends(get_reloj),
) -> PermissionContext:
    """Dependencia FastAPI: valida el access y la sesión en el servidor (una consulta, C-15 D2).

    Los roles del ``PermissionContext`` salen de la base en este pedido, no del token.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de acceso requerido",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(credentials.credentials)
    except Exception:  # token inválido / expirado / sin sid -> 401
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
    try:
        usuario_id = int(payload["sub"])
    except (TypeError, ValueError):
        raise _sesion_invalida()
    contexto = await cargar_contexto(session, sid=payload["sid"], usuario_id=usuario_id)
    if contexto is None or not sesion_vigente(contexto, ahora):
        raise _sesion_invalida()
    # C-13 (D4, O9): la IP real del pedido queda disponible para ``registrar(ip=AUTO)`` en todo el caso de uso.
    contexto_auditoria.set(ip_cliente(request))
    return PermissionContext(
        usuario_id=contexto.usuario_id,
        email=contexto.email,
        roles=contexto.roles,
        jti=str(payload.get("jti", "")),
        sid=str(payload["sid"]),
    )


def require_role(rol_requerido: str):
    """Dependencia parametrizable: inyecta PermissionContext y exige un rol."""

    async def _dependency(context: PermissionContext = Depends(get_current_user)):
        return context.require_role(rol_requerido)

    return _dependency


async def require_recepcion_o_admin(context: PermissionContext = Depends(get_current_user)) -> PermissionContext:
    """Exige rol recepcion u admin; cualquier otro rol -> 403 (movida desde ``catalogo.router`` en C-11)."""
    if not (context.tiene_rol("recepcion") or context.tiene_rol("admin")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Rol requerido: recepcion o admin",
        )
    return context


async def require_admin(context: PermissionContext = Depends(get_current_user)) -> PermissionContext:
    """Exige rol admin; cualquier otro rol -> 403 (consulta de la auditoría y directorio de usuarios, C-13 O6)."""
    if not context.tiene_rol("admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Rol requerido: admin")
    return context
