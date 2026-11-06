"""Máquina de estados del turno y sus efectos sobre la seña (D7). Pura, sin I/O.

Reglas: R9 / RN-SN-02 (ausente no reembolsa), RN-SN-04 (cancelación con 24 h o más devuelve
la seña), RN-SN-05 (pago sobre turno no vigente: a reembolsar), RN-TU-01 (ventana de 24 h).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

VENTANA_CANCELACION = timedelta(hours=24)

TRANSICIONES_TURNO: dict[str, frozenset[str]] = {
    "en_espera": frozenset({"reservado", "cancelado"}),
    "reservado": frozenset({"confirmado", "cancelado", "ausente", "atendido"}),
    "confirmado": frozenset({"cancelado", "ausente", "atendido"}),
}


class TransicionInvalidaError(Exception):
    """El turno no puede pasar de ``actual`` a ``destino`` (409 ``transicion_invalida``)."""

    def __init__(self, actual: str, destino: str) -> None:
        super().__init__(f"Transición inválida: {actual} -> {destino}")
        self.actual = actual
        self.destino = destino


class CancelacionFueraDePlazoError(Exception):
    """Faltan menos de 24 h para el inicio: no se puede cancelar (409 ``fuera_de_plazo``, RN-TU-01)."""

    def __init__(self) -> None:
        super().__init__("La cancelación requiere 24 h o más de anticipación")


@dataclass(frozen=True)
class ResultadoTransicion:
    """Estado final del turno y, si cambia, el nuevo estado del pago de la seña."""

    estado_turno: str
    estado_pago: str | None


def transicionar(actual: str, destino: str) -> str:
    """Valida la transición y devuelve el destino; los estados finales no salen."""
    if destino not in TRANSICIONES_TURNO.get(actual, frozenset()):
        raise TransicionInvalidaError(actual, destino)
    return destino


def aplicar_transicion(actual: str, destino: str, *, estado_pago: str | None, inicio: datetime,
                       ahora: datetime) -> ResultadoTransicion:
    """Valida la transición y calcula el efecto sobre la seña activa del turno."""
    transicionar(actual, destino)
    nuevo_pago: str | None = None
    if destino == "ausente" and estado_pago == "acreditado":
        nuevo_pago = "no_reembolsado"  # R9: el ausente no recibe reembolso
    elif destino == "cancelado":
        if actual in ("reservado", "confirmado"):
            if inicio - ahora < VENTANA_CANCELACION:  # exactamente 24 h se acepta
                raise CancelacionFueraDePlazoError()
            if estado_pago == "acreditado":
                nuevo_pago = "a_reembolsar"  # RN-SN-04: la devolución es manual
        elif estado_pago == "pendiente":  # en_espera -> cancelado
            nuevo_pago = "vencido"
    return ResultadoTransicion(estado_turno=destino, estado_pago=nuevo_pago)
