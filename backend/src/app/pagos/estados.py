"""Máquina de estados del turno y sus efectos sobre la seña (D7). Pura, sin I/O.

Reglas: R9 / RN-SN-02 (ausente no reembolsa), RN-SN-04 (cancelación con 24 h o más devuelve
la seña), RN-SN-05 (pago sobre turno no vigente: a reembolsar), RN-TU-01 (ventana de 24 h).
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta, tzinfo

VENTANA_CANCELACION = timedelta(hours=24)

TRANSICIONES_TURNO: dict[str, frozenset[str]] = {
    "en_espera": frozenset({"reservado", "cancelado"}),
    "reservado": frozenset({"confirmado", "cancelado", "ausente", "atendido"}),
    "confirmado": frozenset({"cancelado", "ausente", "atendido"}),
}


def _exigir_zona(valor: datetime, nombre: str) -> None:
    if valor.tzinfo is None or valor.utcoffset() is None:
        raise ValueError(f"{nombre} debe tener zona horaria (R4)")


def dentro_de_ventana(inicio: datetime, ahora: datetime) -> bool:
    """True si faltan 24 h o más para ``inicio`` (RN-TU-01/02). Compara instantes absolutos.

    Es la única fuente de la regla: la usan la cancelación (``aplicar_transicion``) y la reprogramación.
    Exactamente 24 h se acepta; un inicio ya pasado nunca está dentro de la ventana.
    """
    _exigir_zona(inicio, "inicio")
    _exigir_zona(ahora, "ahora")
    return inicio - ahora >= VENTANA_CANCELACION


def limite_cambios(inicio: datetime, zona: tzinfo) -> datetime:
    """Último instante para cancelar o reprogramar (inicio menos 24 h), con el offset de la clínica."""
    _exigir_zona(inicio, "inicio")
    return (inicio - VENTANA_CANCELACION).astimezone(zona)


def ausente_habilitado_desde(inicio: datetime, tolerancia: timedelta) -> datetime:
    """Primer instante en que se puede marcar ``ausente``: el inicio más la tolerancia (RN-TU-12, O14)."""
    _exigir_zona(inicio, "inicio")
    return inicio + tolerancia


def atendido_habilitado_desde(inicio: datetime, zona: tzinfo) -> datetime:
    """Primer instante en que se puede marcar ``atendido``: las 00:00 del día local del turno (RN-TU-12, O14).

    La persona puede entrar antes de su hora, pero nunca se marca un día anterior al del turno.
    """
    _exigir_zona(inicio, "inicio")
    dia_local = inicio.astimezone(zona).date()
    return datetime.combine(dia_local, time.min, tzinfo=zona)


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
            if not dentro_de_ventana(inicio, ahora):  # exactamente 24 h se acepta
                raise CancelacionFueraDePlazoError()
            if estado_pago == "acreditado":
                nuevo_pago = "a_reembolsar"  # RN-SN-04: la devolución es manual
        elif estado_pago == "pendiente":  # en_espera -> cancelado
            nuevo_pago = "vencido"
    return ResultadoTransicion(estado_turno=destino, estado_pago=nuevo_pago)
