"""Errores de negocio del catálogo y su traducción HTTP (C-14; D1, D3, D4, D5).

Todo rechazo previsible es 404/409/422 con ``motivo`` (R15): nunca un 500. Los manejadores se registran con
``registrar_handlers`` desde ``app.main``.
"""

from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.shared.exceptions import NoReservableError

MENSAJE_EN_USO = (
    "No se puede borrar porque tiene turnos registrados. Podés desactivarlo para que no se ofrezca más."
)


class CatalogoEnUsoError(Exception):
    """Un tratamiento, profesional o sillón tiene turnos, líneas de presupuesto o una conexión de calendario (409)."""


class DuplicadoError(Exception):
    """Nombre de tratamiento o sillón, o matrícula, ya existente sin distinguir mayúsculas ni espacios (409)."""

    def __init__(self, campo: str | None) -> None:
        super().__init__(f"Ya existe un registro con ese valor de {campo or 'campo único'}")
        self.campo = campo


class FranjaSuperpuestaError(Exception):
    """La franja activa se superpone con otra del mismo profesional y día (409); ``franja`` es la que choca."""

    def __init__(self, franja: dict[str, Any] | None) -> None:
        super().__init__("La franja se superpone con otra franja activa del mismo profesional y día")
        self.franja = franja


class DatoInvalidoError(Exception):
    """Dato que no cumple una regla de borde combinada con lo guardado (422, mismo formato que la validación de FastAPI)."""

    def __init__(self, campo: str | None, mensaje: str) -> None:
        super().__init__(mensaje)
        self.campo = campo
        self.mensaje = mensaje


async def en_uso_handler(request: object, exc: CatalogoEnUsoError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": MENSAJE_EN_USO, "motivo": "en_uso"})


async def duplicado_handler(request: object, exc: DuplicadoError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc), "motivo": "duplicado", "campo": exc.campo})


async def franja_superpuesta_handler(request: object, exc: FranjaSuperpuestaError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={"detail": str(exc), "motivo": "franja_superpuesta", "franja": exc.franja},
    )


async def dato_invalido_handler(request: object, exc: DatoInvalidoError) -> JSONResponse:
    loc = ["body", exc.campo] if exc.campo else ["body"]
    return JSONResponse(status_code=422, content={"detail": [{"type": "value_error", "loc": loc, "msg": exc.mensaje}]})


async def no_reservable_handler(request: object, exc: NoReservableError) -> JSONResponse:
    """Lo inactivo no se ofrece ni se reserva (reserva pública y alta manual, C-14 D7 y D8)."""
    return JSONResponse(status_code=422, content={"detail": str(exc), "motivo": "no_reservable", "campo": exc.campo})


def registrar_handlers(app: FastAPI) -> None:
    app.add_exception_handler(CatalogoEnUsoError, en_uso_handler)  # type: ignore[arg-type]
    app.add_exception_handler(DuplicadoError, duplicado_handler)  # type: ignore[arg-type]
    app.add_exception_handler(FranjaSuperpuestaError, franja_superpuesta_handler)  # type: ignore[arg-type]
    app.add_exception_handler(DatoInvalidoError, dato_invalido_handler)  # type: ignore[arg-type]
    app.add_exception_handler(NoReservableError, no_reservable_handler)  # type: ignore[arg-type]
