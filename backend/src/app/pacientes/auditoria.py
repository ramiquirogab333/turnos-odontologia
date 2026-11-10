"""Auditoría de accesos y escrituras sobre datos de salud (C-11, D3; O5, RN-GL-01, R19).

El registro se agrega a la sesión del caso de uso: se confirma o se revierte con él (misma transacción). Nunca lleva
contenido clínico ni datos personales: una clave prohibida hace fallar la llamada.
"""

from collections.abc import Mapping
from typing import Any, Final

from app.models.core import RegistroAuditoria
from sqlalchemy.ext.asyncio import AsyncSession

CLAVES_PROHIBIDAS: Final[frozenset[str]] = frozenset({
    "alergias", "medicacion", "antecedentes_medicos", "observaciones", "nota", "estado_odontograma",
    "nombre", "apellido", "dni", "numero_afiliado", "telefono", "email",
})


class DatosProhibidosEnAuditoriaError(ValueError):
    """Los datos a auditar traen una clave con contenido clínico o personal."""


def _revisar(datos: Any) -> None:
    if isinstance(datos, Mapping):
        for clave, valor in datos.items():
            if clave in CLAVES_PROHIBIDAS:
                raise DatosProhibidosEnAuditoriaError(f"No se audita '{clave}' (R19, Ley 25.326)")
            _revisar(valor)
    elif isinstance(datos, (list, tuple)):
        for item in datos:
            _revisar(item)


def auditar(session: AsyncSession, usuario_id: int, accion: str, entidad: str, entidad_id: int | str,
            datos: Mapping[str, Any] | None = None) -> None:
    """Agrega el registro a la transacción en curso; el caller hace ``commit``."""
    _revisar(datos)
    session.add(RegistroAuditoria(usuario_id=usuario_id, accion=accion, entidad=entidad,
                                  entidad_id=str(entidad_id), datos_despues=dict(datos) if datos else None))
