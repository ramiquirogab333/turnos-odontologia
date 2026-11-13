"""Errores de dominio de la integración con Google Calendar (C-10). Cada uno se traduce a HTTP en el router."""


class GcalNoConfiguradoError(Exception):
    """Faltan las credenciales de Google en el entorno (503 ``gcal_no_configurado``)."""

    def __init__(self) -> None:
        super().__init__("Google Calendar no está configurado en este entorno")


class ConexionActivaError(Exception):
    """La profesional ya tiene la conexión activa (409 ``conexion_activa``)."""

    def __init__(self) -> None:
        super().__init__("Google Calendar ya está conectado")


class ConexionInexistenteError(Exception):
    """No hay conexión para esa profesional (404 ``conexion_inexistente``)."""

    def __init__(self) -> None:
        super().__init__("No hay una conexión de Google Calendar para esa profesional")


class SinPermisoSobreConexionError(Exception):
    """Una odontóloga intentó operar la conexión de otra profesional (403 ``conexion_ajena``)."""

    def __init__(self) -> None:
        super().__init__("Solo la propia profesional o un administrador puede hacerlo")


class ConflictoInexistenteError(Exception):
    """404 ``conflicto_inexistente``."""

    def __init__(self) -> None:
        super().__init__("El conflicto no existe")


class ConflictoCerradoError(Exception):
    """El conflicto ya estaba resuelto, o se cerró solo (409 ``conflicto_cerrado``)."""

    def __init__(self) -> None:
        super().__init__("El conflicto ya no está abierto")


class AccionNoValidaError(Exception):
    """La acción no corresponde al tipo de conflicto (422 ``accion_no_valida``)."""

    def __init__(self) -> None:
        super().__init__("Esa acción no corresponde a este tipo de conflicto")
