"""Acciones que el servidor informa para cada turno de la agenda (C-08, D2/D4). Función pura, sin I/O."""

from datetime import datetime, timedelta, tzinfo
from typing import Literal

from app.pagos.estados import (
    ausente_habilitado_desde,
    atendido_habilitado_desde,
    deshacer_dentro_de_plazo,
    dentro_de_ventana,
)

Accion = Literal["atendido", "ausente", "cancelar", "deshacer_atendido"]
# Qué escritura tiene quien consulta (C-11, O15): recepción/admin todo; la odontóloga solo "atendido"; nadie más.
Permiso = Literal["total", "solo_atendido", "ninguno"]


def acciones_permitidas(estado: str, inicio: datetime, ahora: datetime, permiso: Permiso, zona: tzinfo,
                        tolerancia: timedelta) -> list[Accion]:
    """Acciones que quien consulta puede hacer YA sobre el turno; las mismas reglas que aplican los endpoints.

    - ``atendido``: ``reservado``/``confirmado`` desde las 00:00 del día local del turno (RN-TU-12).
    - ``ausente``: ``reservado``/``confirmado`` desde el inicio más la tolerancia (RN-TU-12).
    - ``cancelar``: ``reservado``/``confirmado`` con 24 h o más (RN-TU-01); ``en_espera`` siempre (O12).
    - ``deshacer_atendido``: ``atendido`` hasta 7 días después del inicio, solo con permiso ``total`` (C-12).
    Con permiso ``solo_atendido`` (odontóloga, O15) la única acción posible es ``atendido``, en las mismas condiciones;
    con ``ninguno`` y en estados finales no hay ninguna.
    """
    if permiso == "ninguno":
        return []
    acciones: list[Accion] = []
    if estado in ("reservado", "confirmado"):
        if ahora >= atendido_habilitado_desde(inicio, zona):
            acciones.append("atendido")
        if ahora >= ausente_habilitado_desde(inicio, tolerancia):
            acciones.append("ausente")
        if dentro_de_ventana(inicio, ahora):
            acciones.append("cancelar")
    elif estado == "en_espera":
        acciones.append("cancelar")
    elif estado == "atendido" and permiso == "total" and deshacer_dentro_de_plazo(inicio, ahora):
        acciones.append("deshacer_atendido")  # C-12 O7/O8: solo recepción y admin, hasta 7 días después del inicio
    if permiso == "solo_atendido":
        return [a for a in acciones if a == "atendido"]
    return acciones
