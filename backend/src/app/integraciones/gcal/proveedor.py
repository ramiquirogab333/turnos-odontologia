"""Puerto del proveedor de calendario (C-10, D1): el dominio no conoce HTTP ni la API de Google.

Implementaciones: ``proveedor_http.ProveedorHttp`` (Calendar v3 con ``httpx`` asíncrono, solo desde el worker salvo el
canje OAuth, R16) y ``proveedor_falso.ProveedorFalso`` (memoria, para pytest). Ningún error ni log lleva un token.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from app.integraciones.gcal.contenido import ContenidoEvento


class ErrorProveedor(Exception):
    """Falla permanente o desconocida de Google (sin datos sensibles en el mensaje)."""

    def __init__(self, mensaje: str = "Error de Google Calendar", codigo: int | None = None) -> None:
        super().__init__(mensaje)
        self.codigo = codigo


class ErrorTransitorio(ErrorProveedor):
    """Red, timeout, 429 o 5xx: se reintenta con espera creciente (O13)."""

    def __init__(self, codigo: int | None = None) -> None:
        super().__init__(f"Google Calendar no disponible (código {codigo if codigo is not None else 'red'})", codigo)


class EventoDuplicado(ErrorProveedor):
    """409: el id ya existe (creado por un ciclo anterior o borrado antes; Google no reutiliza ids)."""

    def __init__(self) -> None:
        super().__init__("El evento ya existe", 409)


class EventoInexistente(ErrorProveedor):
    """404/410: el evento ya no está en Google."""

    def __init__(self) -> None:
        super().__init__("El evento no existe", 404)


class EtagDesactualizado(ErrorProveedor):
    """412: el evento cambió en Google desde la última lectura."""

    def __init__(self) -> None:
        super().__init__("El evento cambió en Google", 412)


class SyncTokenVencido(ErrorProveedor):
    """410 al leer cambios: hay que releer el horizonte completo."""

    def __init__(self) -> None:
        super().__init__("El syncToken venció", 410)


class AccesoRevocado(ErrorProveedor):
    """``invalid_grant``: la profesional quitó el acceso (o la clave de cifrado no sirve)."""

    def __init__(self) -> None:
        super().__init__("Google rechazó la renovación del acceso", 400)


class ErrorAutorizacion(ErrorProveedor):
    """El canje del código OAuth fue rechazado."""

    def __init__(self) -> None:
        super().__init__("Google rechazó la autorización", 400)


@dataclass(frozen=True)
class TokensGoogle:
    access_token: str
    expira_en: datetime
    refresh_token: str | None = None
    email: str | None = None

    def __repr__(self) -> str:  # nunca un token en un log o un assert
        return "TokensGoogle(...)"


@dataclass(frozen=True)
class EventoGoogle:
    """Lo mínimo de un evento que el sistema necesita (sin título, descripción, lugar ni invitados: O19)."""

    id: str
    estado: str  # 'confirmed' | 'cancelled' | 'tentative'
    inicio: datetime | None
    fin: datetime | None
    ocupa: bool  # opaque, no cancelado y no rechazado por la profesional
    etag: str | None
    propias: dict[str, str] = field(default_factory=dict)  # extendedProperties.private


@dataclass(frozen=True)
class CambiosGoogle:
    eventos: list[EventoGoogle]
    sync_token: str | None


class ProveedorCalendario(Protocol):
    async def canjear_codigo(self, codigo: str, verificador: str, redirect_uri: str) -> TokensGoogle: ...

    async def renovar_token(self, refresh_token: str) -> TokensGoogle: ...

    async def revocar(self, token: str) -> None: ...

    async def insertar(self, acceso: str, calendario_id: str, evento_id: str,
                       contenido: ContenidoEvento) -> EventoGoogle: ...

    async def actualizar(self, acceso: str, calendario_id: str, evento_id: str, contenido: ContenidoEvento,
                         etag: str) -> EventoGoogle: ...

    async def borrar(self, acceso: str, calendario_id: str, evento_id: str) -> None: ...

    async def obtener(self, acceso: str, calendario_id: str, evento_id: str) -> EventoGoogle | None: ...

    async def listar(self, acceso: str, calendario_id: str, sync_token: str | None, desde: datetime | None,
                     hasta: datetime | None) -> CambiosGoogle: ...
