"""Mensaje de recordatorio y link ``wa.me`` (C-09, D4). Funciones puras: sin base, sin reloj, sin logs (R19).

El mensaje no se guarda ni se loguea: lleva nombre, horario y, si el turno tiene código de gestión, los enlaces
``/confirmar#<código>`` y ``/gestionar#<código>`` (el código solo viaja en el fragmento, nunca en una consulta).
"""

import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_E164 = re.compile(r"^\+[1-9][0-9]{1,14}$")


@dataclass(frozen=True)
class DatosMensaje:
    """Datos mínimos para redactar el recordatorio."""

    nombre: str | None
    inicio: datetime
    profesional: str
    tratamiento: str
    codigo_gestion: str | None


def armar_mensaje(datos: DatosMensaje, zona: ZoneInfo, base_url: str, clinica: str) -> str:
    """Plantilla fija en español (O15) con día y hora en la zona de la clínica."""
    local = datos.inicio.astimezone(zona)
    cuando = f"{DIAS[local.weekday()]} {local:%d/%m} a las {local:%H:%M}"
    saludo = f"Hola {datos.nombre}" if datos.nombre else "Hola"
    cuerpo = (f"{saludo}, te recordamos tu turno en {clinica}: {cuando}, con {datos.profesional} "
              f"({datos.tratamiento}).")
    if datos.codigo_gestion:
        base = base_url.rstrip("/")
        return (f"{cuerpo}\n\nConfirmá tu asistencia acá: {base}/confirmar#{datos.codigo_gestion}\n"
                f"Si necesitás cancelar o cambiar el horario: {base}/gestionar#{datos.codigo_gestion}")
    return f"{cuerpo}\n\nRespondé este mensaje para confirmar tu asistencia o si necesitás cancelar."


def link_wa_me(telefono_e164: str, texto: str) -> str:
    """``https://wa.me/<dígitos>?text=<texto codificado>``; el teléfono se usa tal cual, sin el ``+`` (O16)."""
    if not _E164.fullmatch(telefono_e164):
        raise ValueError("el teléfono debe estar en formato E.164")
    return f"https://wa.me/{telefono_e164[1:]}?text={quote(texto, safe='')}"
