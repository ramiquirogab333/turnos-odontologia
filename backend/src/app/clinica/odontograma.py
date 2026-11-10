"""Catálogo FDI y estado vigente del odontograma (C-11, D5; O7, O8). Puro, sin I/O."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

PIEZAS_FDI: Final[tuple[int, ...]] = tuple(
    pieza
    for cuadrante, ultimo in ((1, 8), (2, 8), (3, 8), (4, 8), (5, 5), (6, 5), (7, 5), (8, 5))
    for pieza in range(cuadrante * 10 + 1, cuadrante * 10 + ultimo + 1)
)
CARAS: Final[tuple[str, ...]] = ("O", "M", "D", "V", "L")
ESTADOS_CARA: Final[tuple[str, ...]] = ("caries", "obturado")
ESTADOS_PIEZA: Final[tuple[str, ...]] = ("ausente", "extraccion_indicada", "corona", "endodoncia", "implante")
SANO: Final = "sano"
ESTADOS: Final[tuple[str, ...]] = (SANO, *ESTADOS_CARA, *ESTADOS_PIEZA)


def registro_valido(pieza: int, cara: str | None, estado: str) -> bool:
    """Pieza FDI válida, cara del catálogo y coherencia cara/estado (la misma regla que el CHECK de la base)."""
    if pieza not in PIEZAS_FDI or (cara is not None and cara not in CARAS):
        return False
    if estado == SANO:
        return True
    if estado in ESTADOS_CARA:
        return cara is not None
    return estado in ESTADOS_PIEZA and cara is None


@dataclass(frozen=True)
class RegistroOdonto:
    id: int
    pieza: int
    cara: str | None
    estado: str
    registrado_en: datetime


@dataclass
class VigentePieza:
    estado_pieza: str | None = None
    caras: dict[str, str] = field(default_factory=dict)


def vigente(registros: Iterable[RegistroOdonto]) -> dict[int, VigentePieza]:
    """Estado vigente por pieza: recorre en orden ``(registrado_en, id)``; las piezas sin hallazgos no figuran."""
    piezas: dict[int, VigentePieza] = {}
    for r in sorted(registros, key=lambda x: (x.registrado_en, x.id)):
        actual = piezas.setdefault(r.pieza, VigentePieza())
        if r.estado == SANO:
            if r.cara is None:
                actual.estado_pieza, actual.caras = None, {}
            else:
                actual.caras.pop(r.cara, None)
        elif r.estado in ESTADOS_CARA and r.cara is not None:
            actual.caras[r.cara] = r.estado
        else:
            actual.estado_pieza = r.estado
    return {p: v for p, v in piezas.items() if v.estado_pieza is not None or v.caras}
