"""Domain exceptions with HTTP mapping (409 never 500 for 23P01).

Plain Exception subclasses (NOT frozen dataclasses: raising must be able to
attach ``__traceback__``).
"""


class OverlapError(Exception):
    """A turno overlaps another blocking turno on a shared resource."""

    def __init__(self, motivo: str) -> None:
        super().__init__(f"Solape por {motivo}")
        self.motivo = motivo


class PastStartError(Exception):
    """The requested inicio is in the past."""


class NoReservableError(Exception):
    """El tratamiento, profesional o sillón existe pero está inactivo o fuera de servicio: no se ofrece para turnos nuevos
    (C-14, 422 ``no_reservable``). ``campo`` dice cuál."""

    def __init__(self, campo: str) -> None:
        super().__init__(f"No se ofrece para reservar: {campo}")
        self.campo = campo


class ReferenceNotFoundError(Exception):
    """A referenced FK parent does not exist."""

    def __init__(self, campo: str) -> None:
        super().__init__(f"Referencia inexistente: {campo}")
        self.campo = campo
