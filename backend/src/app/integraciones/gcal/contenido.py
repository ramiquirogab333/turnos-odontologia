"""Contenido del evento de Google Calendar (C-10, D5, O8, O17). Funciones puras, sin base ni red.

El evento NUNCA lleva nombre, teléfono, DNI, email ni código de gestión del paciente (Ley 25.326, R19): solo el
tratamiento, el sillón y un enlace al panel. Las propiedades privadas lo marcan como "del sistema" para el pull.
"""

import base64
import hashlib
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

MARCA_SISTEMA = "turnos_sistema"


@dataclass(frozen=True)
class ContenidoEvento:
    """Lo que el sistema escribe en Google para un turno."""

    titulo: str
    descripcion: str
    inicio: datetime  # con zona (hora de la clínica)
    fin: datetime
    zona: str
    propiedades_privadas: dict[str, str]


def armar_contenido(*, turno_id: int, tratamiento: str, sillon: str, inicio: datetime, fin: datetime,
                    zona: ZoneInfo, url_panel: str) -> ContenidoEvento:
    """Título "Turno · <tratamiento>", descripción con sillón y enlace a la agenda del día; horario en ``zona``."""
    local_inicio = inicio.astimezone(zona)
    descripcion = f"{sillon}\n{url_panel}/#/agenda?fecha={local_inicio.date().isoformat()}"
    return ContenidoEvento(
        titulo=f"Turno · {tratamiento}", descripcion=descripcion, inicio=local_inicio, fin=fin.astimezone(zona),
        zona=zona.key, propiedades_privadas={MARCA_SISTEMA: "1", "turno_id": str(turno_id)})


def id_evento(turno_id: int, conexion_id: int, generacion: int) -> str:
    """Id determinista (O17) en base32hex minúscula sin relleno: el alfabeto ``a-v0-9`` que exige Google (5-1024)."""
    crudo = f"t{turno_id}c{conexion_id}g{generacion}".encode()
    return base64.b32hexencode(crudo).decode().lower().rstrip("=")


def hash_contenido(contenido: ContenidoEvento) -> str:
    """Huella del título, la descripción y el horario empujados: detecta que el turno cambió desde el último push."""
    texto = "\n".join([contenido.titulo, contenido.descripcion, contenido.inicio.isoformat(),
                       contenido.fin.isoformat()])
    return hashlib.sha256(texto.encode()).hexdigest()
