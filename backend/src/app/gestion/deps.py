"""Dependencias inyectables de la gestión del turno. Los tests las sobreescriben con ``dependency_overrides``."""

from datetime import datetime, timezone

from app.gestion.eventos import NotificadorTurnos
from app.integraciones.gcal.notificador import NotificadorCalendario
from app.notificaciones.notificador import NotificadorCompuesto, NotificadorRecordatorios
from app.shared.db import get_session_factory


def get_reloj() -> datetime:
    """El 'ahora' del servidor (con zona). Se inyecta para que la ventana de 24 h sea testeable sin reloj real."""
    return datetime.now(timezone.utc)


def get_notificador() -> NotificadorTurnos:
    """Puerto de eventos: recordatorios (C-09) y Google Calendar (C-10, solo marca pendiente; no llama a Google)."""
    factory = get_session_factory()
    return NotificadorCompuesto([NotificadorRecordatorios(factory), NotificadorCalendario(factory)])
