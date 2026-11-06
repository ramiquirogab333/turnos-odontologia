"""Errores de dominio de la gestión del turno por el paciente, con su mapeo HTTP en el router (R13)."""

from datetime import datetime


class GestionNoEncontradaError(Exception):
    """Código ausente, inválido, desconocido o de un turno sin código: siempre el mismo 404 (RN-TU-06)."""

    def __init__(self) -> None:
        super().__init__("No encontramos un turno con ese código")


class FueraDePlazoError(Exception):
    """Faltan menos de 24 h: no se puede cancelar ni reprogramar online (409 ``fuera_de_plazo``, RN-TU-01/02)."""

    def __init__(self, limite_cambios: datetime) -> None:
        super().__init__("Fuera de plazo")
        self.limite_cambios = limite_cambios


class TurnoNoModificableError(Exception):
    """El turno está en un estado final (409 ``turno_no_modificable``)."""

    def __init__(self, estado: str) -> None:
        super().__init__(f"El turno está {estado}")
        self.estado = estado


class SenaPendienteError(Exception):
    """Una pre-reserva ``en_espera`` no se reprograma: se cancela y se reserva otro horario (409, O3)."""

    def __init__(self) -> None:
        super().__init__("Tu turno todavía no está confirmado. Cancelalo y reservá otro horario.")


class HorarioInvalidoError(Exception):
    """El nuevo inicio es el mismo horario o ya pasó (422 ``mismo_horario`` / ``horario_pasado``)."""

    def __init__(self, motivo: str) -> None:
        super().__init__("Elegí un horario futuro distinto del actual" if motivo == "mismo_horario"
                         else "El horario elegido ya pasó")
        self.motivo = motivo
