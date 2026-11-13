"""Auditoría de accesos y escrituras sobre datos de salud (C-11, D3; O5, RN-GL-01, R19).

Desde C-13 (D2) la escritura vive en ``app.plataforma.auditoria``; este módulo conserva la firma de C-11 y reexporta la
guarda para no romper imports.
"""

from collections.abc import Mapping
from typing import Any

from app.plataforma.auditoria import CLAVES_PROHIBIDAS, DatosProhibidosEnAuditoriaError, registrar
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["CLAVES_PROHIBIDAS", "DatosProhibidosEnAuditoriaError", "auditar"]


def auditar(session: AsyncSession, usuario_id: int, accion: str, entidad: str, entidad_id: int | str,
            datos: Mapping[str, Any] | None = None) -> None:
    """Agrega el registro a la transacción en curso; el caller hace ``commit``."""
    registrar(session, accion=accion, entidad=entidad, entidad_id=entidad_id, usuario_id=usuario_id, despues=datos)
