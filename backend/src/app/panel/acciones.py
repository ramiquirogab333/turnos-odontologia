"""Acciones que el servidor informa para cada turno de la agenda (C-08, D2/D4). Función pura, sin I/O."""

from datetime import datetime, timedelta, tzinfo
from typing import Literal

from app.pagos.estados import ausente_habilitado_desde, atendido_habilitado_desde, dentro_de_ventana

Accion = Literal["atendido", "ausente", "cancelar"]


def acciones_permitidas(estado: str, inicio: datetime, ahora: datetime, puede_escribir: bool, zona: tzinfo,
                        tolerancia: timedelta) -> list[Accion]:
    """Acciones que quien consulta puede hacer YA sobre el turno; las mismas reglas que aplican los endpoints.

    - ``atendido``: ``reservado``/``confirmado`` desde las 00:00 del día local del turno (RN-TU-12).
    - ``ausente``: ``reservado``/``confirmado`` desde el inicio más la tolerancia (RN-TU-12).
    - ``cancelar``: ``reservado``/``confirmado`` con 24 h o más (RN-TU-01); ``en_espera`` siempre (O12).
    Sin permiso de escritura (odontólogo, O5) y en estados finales no hay ninguna.
    """
    if not puede_escribir:
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
    return acciones
