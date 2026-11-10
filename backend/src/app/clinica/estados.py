"""Máquina de estados del presupuesto (C-11, D7; O10). Pura, sin I/O."""

from typing import Final

from app.pagos.estados import TransicionInvalidaError

ESTADOS: Final[tuple[str, ...]] = ("borrador", "presentado", "aceptado", "rechazado", "anulado")

TRANSICIONES: Final[dict[str, frozenset[str]]] = {
    "borrador": frozenset({"presentado", "anulado"}),
    "presentado": frozenset({"aceptado", "rechazado", "anulado"}),
    "aceptado": frozenset({"anulado"}),
}


def validar_transicion(actual: str, destino: str) -> None:
    """Lanza ``TransicionInvalidaError`` (409 ``transicion_invalida``) si ``actual -> destino`` no está permitida."""
    if destino not in TRANSICIONES.get(actual, frozenset()):
        raise TransicionInvalidaError(actual, destino)
