"""El 'ahora' del servidor, inyectable (C-07, C-15): los tests lo sobreescriben con ``dependency_overrides``."""

from datetime import datetime, timezone


def get_reloj() -> datetime:
    """El 'ahora' del servidor (con zona). Se inyecta para que ventanas y vencimientos sean testeables sin dormir."""
    return datetime.now(timezone.utc)
