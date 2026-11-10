"""Errores de dominio de pacientes, ficha y datos clínicos, con su mapeo HTTP en los routers (R13)."""


class PacienteInexistenteError(Exception):
    """El paciente no existe (404). Se valida antes que el alcance y nunca se audita."""

    def __init__(self) -> None:
        super().__init__("No encontramos a ese paciente")


class PacienteAjenoError(Exception):
    """La odontóloga no tiene acceso a este paciente (403 ``paciente_ajeno``, O2)."""

    def __init__(self) -> None:
        super().__init__("Este paciente no figura entre tus pacientes atendidos")


class AccesoClinicoVencidoError(Exception):
    """Acceso de solo lectura: la última atención pasó la ventana y no hay turno pendiente (403, O16)."""

    def __init__(self) -> None:
        super().__init__("Tu acceso para editar a este paciente venció: pedí un turno a recepción")


class DniDuplicadoError(Exception):
    """Ya existe un paciente con ese DNI (409 ``dni_duplicado``)."""

    def __init__(self) -> None:
        super().__init__("Ya hay un paciente con ese DNI")


class ObraSocialInactivaError(Exception):
    """La obra social no existe o está inactiva (422 ``obra_social_inactiva``)."""

    def __init__(self) -> None:
        super().__init__("La obra social no existe o está inactiva")


class VersionDesactualizadaError(Exception):
    """La ficha cambió desde que se leyó (409 ``version_desactualizada``, O6)."""

    def __init__(self) -> None:
        super().__init__("La ficha cambió: volvé a cargarla y repetí la edición")
