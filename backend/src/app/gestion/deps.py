"""Dependencias inyectables de la gestión del turno. Los tests las sobreescriben con ``dependency_overrides``."""

from datetime import datetime, timezone

from app.gestion.eventos import NotificadorNulo, NotificadorTurnos


def get_reloj() -> datetime:
    """El 'ahora' del servidor (con zona). Se inyecta para que la ventana de 24 h sea testeable sin reloj real."""
    return datetime.now(timezone.utc)


def get_notificador() -> NotificadorTurnos:
    """Puerto de eventos para C-09/C-10; hoy una implementación nula que solo loguea."""
    return NotificadorNulo()
