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


class ReferenceNotFoundError(Exception):
    """A referenced FK parent does not exist."""

    def __init__(self, campo: str) -> None:
        super().__init__(f"Referencia inexistente: {campo}")
        self.campo = campo
