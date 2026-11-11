"""Errores de dominio de la caja, con su mapeo HTTP en ``caja.http`` (R13)."""

from datetime import date, datetime


class CajaCerradaError(Exception):
    """El día tiene un cierre vigente: no se agregan, quitan ni cambian movimientos (409 ``caja_cerrada``, O2)."""

    def __init__(self, dia: date) -> None:
        super().__init__(f"La caja del {dia.isoformat()} está cerrada")
        self.dia = dia


class DiaNoTerminadoError(Exception):
    """El día todavía no se puede cerrar (409 ``dia_no_terminado``, con el instante desde el que sí, O1)."""

    def __init__(self, cerrable_desde: datetime) -> None:
        super().__init__("El día todavía no terminó: se puede cerrar desde las 00:15 del día siguiente")
        self.cerrable_desde = cerrable_desde


class DiaYaCerradoError(Exception):
    """Ya hay un cierre vigente de ese día (409 ``dia_ya_cerrado``, con su id)."""

    def __init__(self, cierre_id: int) -> None:
        super().__init__("Ese día ya tiene un cierre vigente")
        self.cierre_id = cierre_id


class CierreInexistenteError(Exception):
    """El cierre no existe (404)."""

    def __init__(self) -> None:
        super().__init__("No encontramos ese cierre")
