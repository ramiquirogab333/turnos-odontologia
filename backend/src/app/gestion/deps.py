"""Dependencias inyectables de la gestión del turno. Los tests las sobreescriben con ``dependency_overrides``."""

from app.gestion.eventos import NotificadorTurnos
from app.integraciones.gcal.notificador import NotificadorCalendario
from app.notificaciones.notificador import NotificadorCompuesto, NotificadorRecordatorios
from app.shared.db import get_session_factory
from app.shared.reloj import get_reloj

__all__ = ["get_notificador", "get_reloj"]  # get_reloj vive en app.shared.reloj (C-15) y se reexporta aquí


def get_notificador() -> NotificadorTurnos:
    """Puerto de eventos: recordatorios (C-09) y Google Calendar (C-10, solo marca pendiente; no llama a Google)."""
    factory = get_session_factory()
    return NotificadorCompuesto([NotificadorRecordatorios(factory), NotificadorCalendario(factory)])
