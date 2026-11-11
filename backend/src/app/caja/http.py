"""Traducción de los errores de la caja a respuestas HTTP (C-12, R13/R15). Cuerpo ``ErrorPanelBody`` + datos extra."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.caja.errores import CajaCerradaError, CierreInexistenteError, DiaNoTerminadoError, DiaYaCerradoError
from app.pacientes.http import respuesta
from app.pagos.errores import (
    FechaDevolucionInvalidaError,
    NoEsDevolucionPendienteError,
    NoEstaEnRevisionError,
    PagoNoEncontradoError,
)
from app.panel.service import zona_clinica


def registrar_handlers(app: FastAPI) -> None:
    async def _caja_cerrada(request: Request, exc: CajaCerradaError) -> JSONResponse:
        return respuesta(409, str(exc), "caja_cerrada", dia=exc.dia.isoformat())

    async def _no_terminado(request: Request, exc: DiaNoTerminadoError) -> JSONResponse:
        return respuesta(409, str(exc), "dia_no_terminado",
                         cerrable_desde=exc.cerrable_desde.astimezone(zona_clinica()).isoformat())

    async def _ya_cerrado(request: Request, exc: DiaYaCerradoError) -> JSONResponse:
        return respuesta(409, str(exc), "dia_ya_cerrado", cierre_id=exc.cierre_id)

    async def _inexistente(request: Request, exc: CierreInexistenteError) -> JSONResponse:
        return respuesta(404, str(exc), "cierre_inexistente")

    async def _pago_inexistente(request: Request, exc: PagoNoEncontradoError) -> JSONResponse:
        return respuesta(404, "No encontramos ese pago", "pago_inexistente")

    async def _no_en_revision(request: Request, exc: NoEstaEnRevisionError) -> JSONResponse:
        return respuesta(409, str(exc), "no_esta_en_revision")

    async def _no_pendiente(request: Request, exc: NoEsDevolucionPendienteError) -> JSONResponse:
        return respuesta(409, str(exc), "no_es_devolucion_pendiente")

    async def _fecha(request: Request, exc: FechaDevolucionInvalidaError) -> JSONResponse:
        return respuesta(422, str(exc), exc.motivo)

    app.add_exception_handler(PagoNoEncontradoError, _pago_inexistente)  # type: ignore[arg-type]
    app.add_exception_handler(NoEstaEnRevisionError, _no_en_revision)  # type: ignore[arg-type]
    app.add_exception_handler(NoEsDevolucionPendienteError, _no_pendiente)  # type: ignore[arg-type]
    app.add_exception_handler(FechaDevolucionInvalidaError, _fecha)  # type: ignore[arg-type]
    app.add_exception_handler(CajaCerradaError, _caja_cerrada)  # type: ignore[arg-type]
    app.add_exception_handler(DiaNoTerminadoError, _no_terminado)  # type: ignore[arg-type]
    app.add_exception_handler(DiaYaCerradoError, _ya_cerrado)  # type: ignore[arg-type]
    app.add_exception_handler(CierreInexistenteError, _inexistente)  # type: ignore[arg-type]
