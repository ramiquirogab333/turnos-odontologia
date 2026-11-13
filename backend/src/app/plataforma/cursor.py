"""Cursor keyset opaco de la consulta de auditoría (C-13, D7): ``base64url(json{"t": iso, "id": n})`` validado."""

import base64
import binascii
import json
from datetime import datetime, timezone
from typing import Any


class CursorInvalidoError(ValueError):
    """El cursor no es uno de los que emite el servidor (422 en la API)."""


def codificar_cursor(instante: datetime, registro_id: int) -> str:
    cuerpo = json.dumps({"t": instante.astimezone(timezone.utc).isoformat(), "id": registro_id}, separators=(",", ":"))
    return base64.urlsafe_b64encode(cuerpo.encode()).decode().rstrip("=")


def decodificar_cursor(cursor: str) -> tuple[datetime, int]:
    """``(instante con zona, id)`` del último registro de la página anterior; ``CursorInvalidoError`` si no es válido."""
    try:
        datos: Any = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode())
        instante = datetime.fromisoformat(datos["t"])
        registro_id = datos["id"]
    except (binascii.Error, ValueError, KeyError, TypeError, UnicodeDecodeError) as exc:
        raise CursorInvalidoError("cursor inválido") from exc
    if instante.tzinfo is None or isinstance(registro_id, bool) or not isinstance(registro_id, int) or registro_id < 1:
        raise CursorInvalidoError("cursor inválido")
    return instante, registro_id
