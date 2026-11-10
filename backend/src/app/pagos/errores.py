"""Errores de dominio de la seña, con su mapeo HTTP en los routers (R13)."""

from datetime import datetime


class SenaNoEncontradaError(Exception):
    """Turno inexistente o código de gestión ausente/ajeno: siempre 404, sin revelar cuál (RN-GL, privacidad)."""

    def __init__(self) -> None:
        super().__init__("Turno no encontrado")


class TurnoNoPendienteError(Exception):
    """El turno no está ``en_espera`` o su pre-reserva venció (409 ``estado_invalido``)."""

    def __init__(self, estado: str, vencido: bool = False) -> None:
        super().__init__("La reserva venció" if vencido else f"El turno está {estado}")
        self.estado = estado
        self.vencido = vencido


class MedioNoHabilitadoError(Exception):
    """Medio de pago deshabilitado o sin configurar (422, indica los habilitados)."""

    def __init__(self, medio: str, habilitados: list[str]) -> None:
        super().__init__(f"Medio no habilitado: {medio}")
        self.medio = medio
        self.habilitados = habilitados


class SenaNoRequeridaError(Exception):
    """La seña calculada es 0.00: el turno está exento (RN-SN-06)."""

    def __init__(self) -> None:
        super().__init__("El turno no requiere seña")


class PagoNoAcreditableError(Exception):
    """El pago no se puede acreditar a mano (409): no es transferencia o no está pendiente/vigente."""

    def __init__(self, motivo: str) -> None:
        super().__init__(f"Pago no acreditable: {motivo}")
        self.motivo = motivo


class OperacionReintentableError(Exception):
    """Deadlock o conflicto transitorio que se agotó tras los reintentos: se responde 503 y se reintenta más tarde.

    Nunca se traduce en un reembolso ni en una cancelación: solo un conflicto real de agenda lo hace.
    """

    def __init__(self) -> None:
        super().__init__("La operación no pudo completarse ahora; reintentá en unos instantes")


class PagoNoEncontradoError(Exception):
    """Pago inexistente (404)."""

    def __init__(self) -> None:
        super().__init__("Pago no encontrado")


class TurnoInexistenteError(Exception):
    """El turno no existe (404)."""

    def __init__(self) -> None:
        super().__init__("Turno no encontrado")


class TurnoAjenoError(Exception):
    """La odontóloga pidió marcar un turno que no es de su profesional o que no existe (403 ``turno_ajeno``, O15).

    Un mismo error para "ajeno" e "inexistente": no revela si el turno existe ni en qué estado está.
    """

    def __init__(self) -> None:
        super().__init__("Solo podés marcar tus propios turnos")


class MarcadoNoHabilitadoError(Exception):
    """Todavía no es el momento de marcar el turno como ausente o atendido (409 ``marcado_no_habilitado``, RN-TU-12)."""

    def __init__(self, habilitado_desde: datetime) -> None:
        super().__init__("Todavía no se puede marcar este turno")
        self.habilitado_desde = habilitado_desde
