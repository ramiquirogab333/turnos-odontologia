"""Errores de dominio de presupuestos y pagos de presupuesto, con su mapeo HTTP en ``pacientes.http`` (R13)."""

from decimal import Decimal


class PresupuestoInexistenteError(Exception):
    """El presupuesto no existe o pertenece a otro paciente (404)."""

    def __init__(self) -> None:
        super().__init__("No encontramos ese presupuesto")


class PresupuestoNoEditableError(Exception):
    """Solo un borrador se edita (409 ``presupuesto_no_editable``, O10)."""

    def __init__(self, estado: str) -> None:
        super().__init__(f"El presupuesto está {estado} y ya no se puede editar")
        self.estado = estado


class PresupuestoConPagosError(Exception):
    """Un aceptado con pagos ``registrado`` no se anula (409 ``presupuesto_con_pagos``)."""

    def __init__(self) -> None:
        super().__init__("El presupuesto tiene pagos registrados: anulalos antes de anular el presupuesto")


class TratamientoInexistenteError(Exception):
    """Alguna línea referencia un tratamiento que no existe (422 ``tratamiento_inexistente``)."""

    def __init__(self) -> None:
        super().__init__("Alguno de los tratamientos no existe")


class PresupuestoNoAceptadoError(Exception):
    """Los cobros solo se registran sobre presupuestos aceptados (409 ``presupuesto_no_aceptado``)."""

    def __init__(self, estado: str) -> None:
        super().__init__(f"El presupuesto está {estado}: solo se cobra un presupuesto aceptado")
        self.estado = estado


class MontoExcedeSaldoError(Exception):
    """El pago supera el saldo del presupuesto (409 ``monto_excede_saldo``, con el saldo vigente)."""

    def __init__(self, saldo: Decimal) -> None:
        super().__init__(f"El monto supera el saldo del presupuesto ({saldo:.2f})")
        self.saldo = saldo


class ReferenciaDuplicadaError(Exception):
    """La misma operación ya está registrada para ese medio (409 ``referencia_duplicada``)."""

    def __init__(self) -> None:
        super().__init__("Esa referencia ya está registrada para ese medio de pago")


class FechaCobroFuturaError(Exception):
    """La fecha de cobro no puede ser futura (422 ``fecha_cobro_futura``)."""

    def __init__(self) -> None:
        super().__init__("La fecha de cobro no puede ser futura")


class PagoInexistenteError(Exception):
    """El pago no existe o es de otro presupuesto (404)."""

    def __init__(self) -> None:
        super().__init__("No encontramos ese pago")
