"""Traducción de los errores de dominio de pacientes y datos clínicos a respuestas HTTP (C-11, R13/R15).

Se registran como ``exception_handler`` de la aplicación: así toda ruta que levante estos errores responde igual y
ningún handler olvida un caso. El cuerpo es siempre ``ErrorPanelBody`` (``detail`` + ``motivo`` estable).
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.clinica.errores import (
    FechaCobroFuturaError,
    MontoExcedeSaldoError,
    PagoInexistenteError,
    PresupuestoConPagosError,
    PresupuestoInexistenteError,
    PresupuestoNoAceptadoError,
    PresupuestoNoEditableError,
    ReferenciaDuplicadaError,
    TratamientoInexistenteError,
)
from app.pacientes.errores import (
    AccesoClinicoVencidoError,
    DniDuplicadoError,
    ObraSocialInactivaError,
    PacienteAjenoError,
    PacienteInexistenteError,
    VersionDesactualizadaError,
)
from app.pagos.errores import TurnoInexistenteError
from app.pagos.estados import TransicionInvalidaError
from app.panel.schemas import ErrorPanelBody
from app.panel.service import SinAccesoAlPanelError, SinProfesionalAsociadoError

# (excepción, status, motivo)
_MAPA: tuple[tuple[type[Exception], int, str], ...] = (
    (PacienteInexistenteError, 404, "paciente_inexistente"),
    (PacienteAjenoError, 403, "paciente_ajeno"),
    (AccesoClinicoVencidoError, 403, "acceso_clinico_vencido"),
    (SinAccesoAlPanelError, 403, "sin_acceso_al_panel"),
    (SinProfesionalAsociadoError, 403, "sin_profesional_asociado"),
    (DniDuplicadoError, 409, "dni_duplicado"),
    (ObraSocialInactivaError, 422, "obra_social_inactiva"),
    (VersionDesactualizadaError, 409, "version_desactualizada"),
    (TurnoInexistenteError, 404, "turno_inexistente"),
    (PresupuestoInexistenteError, 404, "presupuesto_inexistente"),
    (PagoInexistenteError, 404, "pago_inexistente"),
    (PresupuestoNoEditableError, 409, "presupuesto_no_editable"),
    (PresupuestoConPagosError, 409, "presupuesto_con_pagos"),
    (PresupuestoNoAceptadoError, 409, "presupuesto_no_aceptado"),
    (ReferenciaDuplicadaError, 409, "referencia_duplicada"),
    (TransicionInvalidaError, 409, "transicion_invalida"),
    (TratamientoInexistenteError, 422, "tratamiento_inexistente"),
    (FechaCobroFuturaError, 422, "fecha_cobro_futura"),
)


def respuesta(status: int, detail: str, motivo: str, **extra: object) -> JSONResponse:
    cuerpo = ErrorPanelBody(detail=detail, motivo=motivo).model_dump(mode="json", exclude_none=True)
    cuerpo.update(extra)
    return JSONResponse(status_code=status, content=cuerpo)


def registrar_handlers(app: FastAPI) -> None:
    for excepcion, status, motivo in _MAPA:
        async def _handler(request: Request, exc: Exception, _s: int = status, _m: str = motivo) -> JSONResponse:
            return respuesta(_s, str(exc), _m)

        app.add_exception_handler(excepcion, _handler)  # type: ignore[arg-type]

    async def _excede_saldo(request: Request, exc: MontoExcedeSaldoError) -> JSONResponse:
        return respuesta(409, str(exc), "monto_excede_saldo", saldo=f"{exc.saldo:.2f}")

    app.add_exception_handler(MontoExcedeSaldoError, _excede_saldo)  # type: ignore[arg-type]
