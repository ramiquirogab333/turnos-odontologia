"""Escritura única de la auditoría (C-13, D2; RN-GL-01, R19, Ley 25.326).

``registrar`` agrega la fila a la sesión del caso de uso: se confirma o se revierte con él (misma transacción). Nunca lleva
contenido clínico, datos personales ni secretos: una clave prohibida (a cualquier nivel) hace fallar la llamada y no se
guarda nada. La IP del pedido en curso la fija ``get_current_user`` en ``contexto_auditoria`` (D4).
"""

from collections.abc import Mapping
from contextvars import ContextVar
from typing import Any, Final

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import RegistroAuditoria

CLAVES_PROHIBIDAS: Final[frozenset[str]] = frozenset({
    # Clínicos y personales (C-11).
    "alergias", "medicacion", "antecedentes_medicos", "observaciones", "nota", "estado_odontograma",
    "nombre", "apellido", "dni", "numero_afiliado", "telefono", "email",
    # Secretos, búsquedas y datos del contacto de la reserva pública (C-13, D2).
    "password", "token", "access_token", "refresh_token", "codigo_gestion", "q", "busqueda", "contacto_nombre",
    "contacto_telefono", "url_autorizacion", "state", "code_verifier",
})


class _Auto:
    """Marca "tomar la IP del pedido en curso" (distinta de ``None``, que es "sin IP")."""

    def __repr__(self) -> str:
        return "AUTO"


AUTO: Final[_Auto] = _Auto()

# IP validada del pedido autenticado en curso; ``None`` fuera de un pedido (trabajos del sistema).
contexto_auditoria: ContextVar[str | None] = ContextVar("contexto_auditoria", default=None)


class DatosProhibidosEnAuditoriaError(ValueError):
    """Los datos a auditar traen una clave con contenido clínico, personal o secreto."""


def _revisar(datos: Any) -> None:
    if isinstance(datos, Mapping):
        for clave, valor in datos.items():
            if clave in CLAVES_PROHIBIDAS:
                raise DatosProhibidosEnAuditoriaError(f"No se audita '{clave}' (R19, Ley 25.326)")
            _revisar(valor)
    elif isinstance(datos, (list, tuple)):
        for item in datos:
            _revisar(item)


def registrar(session: AsyncSession, *, accion: str, entidad: str, entidad_id: int | str | None,
              usuario_id: int | None, antes: Mapping[str, Any] | None = None,
              despues: Mapping[str, Any] | None = None, ip: str | None | _Auto = AUTO) -> None:
    """Agrega el registro a la transacción en curso; el caller hace ``commit``."""
    _revisar(antes)
    _revisar(despues)
    ip_efectiva = contexto_auditoria.get() if isinstance(ip, _Auto) else ip
    session.add(RegistroAuditoria(
        usuario_id=usuario_id, accion=accion, entidad=entidad,
        entidad_id=None if entidad_id is None else str(entidad_id),
        datos_antes=dict(antes) if antes is not None else None,
        datos_despues=dict(despues) if despues is not None else None, ip=ip_efectiva))
