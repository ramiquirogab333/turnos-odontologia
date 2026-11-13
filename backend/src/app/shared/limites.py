"""Límite de solicitudes (C-15, D5/O9): puerto, adaptador en memoria y respuesta 429 común.

El dominio solo conoce el puerto ``LimitadorSolicitudes``; el adaptador de Redis (producción) vive aparte.
Ventana fija por clave: simple, O(1) y atómica. Las claves llevan el email hasheado (sin PII, R19).
"""

import asyncio
import hashlib
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from redis.asyncio import Redis

from app.shared.logger import get_logger
from app.shared.red import ip_cliente
from app.shared.settings import get_settings

logger = get_logger(__name__)

MENSAJE_LIMITE = "Demasiados intentos. Probá de nuevo más tarde."


@dataclass(frozen=True)
class Resultado:
    """Veredicto del limitador para un pedido."""

    permitido: bool
    reintentar_en_segundos: int
    #: ``True`` solo en el primer pedido rechazado de la ventana (para auditar el bloqueo una vez).
    recien_bloqueado: bool = False


class LimitadorSolicitudes(Protocol):
    """Puerto del limitador: el dominio no sabe si detrás hay Redis o memoria."""

    async def consumir(self, clave: str, maximo: int, ventana_segundos: int) -> Resultado:
        """Cuenta un pedido en la clave y dice si entra (cuenta <= máximo)."""
        ...

    async def registrar(self, clave: str, ventana_segundos: int) -> None:
        """Suma un pedido a la clave sin evaluarlo (contadores de fallos)."""
        ...

    async def consultar(self, clave: str, maximo: int) -> Resultado:
        """Dice si la clave ya llegó al máximo, sin sumar un pedido."""
        ...

    async def reiniciar(self, clave: str) -> None:
        """Borra el contador de la clave (idempotente)."""
        ...


class LimiteSuperadoOut(BaseModel):
    """Cuerpo del 429 (R15): idéntico para cualquier clave, sin revelar emails ni cuentas."""

    model_config = ConfigDict(extra="forbid")

    detail: str
    motivo: Literal["demasiados_intentos"]


#: Para ``responses=`` de cada endpoint limitado: el 429 figura en OpenAPI.
RESPUESTA_429_OPENAPI: dict[int | str, dict[str, Any]] = {
    429: {
        "model": LimiteSuperadoOut,
        "description": "Demasiados pedidos; reintentar tras los segundos de Retry-After.",
        "headers": {"Retry-After": {"description": "Segundos de espera", "schema": {"type": "integer", "minimum": 1}}},
    }
}


def respuesta_limite_superado(reintentar_en_segundos: int) -> JSONResponse:
    """429 común con ``Retry-After`` (entero >= 1) y el cuerpo ``LimiteSuperadoOut``."""
    cuerpo = LimiteSuperadoOut(detail=MENSAJE_LIMITE, motivo="demasiados_intentos")
    return JSONResponse(
        status_code=429,
        content=cuerpo.model_dump(),
        headers={"Retry-After": str(max(1, reintentar_en_segundos))},
    )


def clave_email(email: str) -> str:
    """Huella del email normalizado (``strip().lower()``) para las claves: nunca el email en claro."""
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


class _Entrada:
    __slots__ = ("cuenta", "expira", "rechazos")

    def __init__(self, expira: float) -> None:
        self.cuenta = 0
        self.expira = expira
        self.rechazos = 0


class LimitadorEnMemoria:
    """Adaptador en memoria (pytest y desarrollo de un solo proceso); el reloj es inyectable para no dormir."""

    def __init__(self, reloj: Callable[[], float] = time.monotonic) -> None:
        self._reloj = reloj
        self._entradas: dict[str, _Entrada] = {}

    def _vigente(self, clave: str) -> _Entrada | None:
        entrada = self._entradas.get(clave)
        if entrada is not None and self._reloj() >= entrada.expira:
            del self._entradas[clave]
            return None
        return entrada

    def _espera(self, entrada: _Entrada) -> int:
        return max(1, math.ceil(entrada.expira - self._reloj()))

    def _sumar(self, clave: str, ventana_segundos: int) -> _Entrada:
        entrada = self._vigente(clave)
        if entrada is None:
            entrada = self._entradas[clave] = _Entrada(self._reloj() + ventana_segundos)
        entrada.cuenta += 1
        return entrada

    async def consumir(self, clave: str, maximo: int, ventana_segundos: int) -> Resultado:
        entrada = self._sumar(clave, ventana_segundos)
        if entrada.cuenta <= maximo:
            return Resultado(True, self._espera(entrada))
        return Resultado(False, self._espera(entrada), recien_bloqueado=entrada.cuenta == maximo + 1)

    async def registrar(self, clave: str, ventana_segundos: int) -> None:
        self._sumar(clave, ventana_segundos)

    async def consultar(self, clave: str, maximo: int) -> Resultado:
        entrada = self._vigente(clave)
        if entrada is None or entrada.cuenta < maximo:
            return Resultado(True, 0)
        entrada.rechazos += 1
        return Resultado(False, self._espera(entrada), recien_bloqueado=entrada.rechazos == 1)

    async def reiniciar(self, clave: str) -> None:
        self._entradas.pop(clave, None)


class LimitadorRedis:
    """Adaptador de producción: ``INCR`` + ``EXPIRE NX`` atómicos en una transacción y ``TTL`` para ``Retry-After``."""

    def __init__(self, cliente: "Redis[str]") -> None:
        self._r = cliente

    async def _sumar(self, clave: str, ventana_segundos: int) -> tuple[int, int]:
        async with self._r.pipeline(transaction=True) as tuberia:
            tuberia.incr(clave)
            tuberia.expire(clave, ventana_segundos, nx=True)
            tuberia.ttl(clave)
            cuenta, _, ttl = await tuberia.execute()
        return int(cuenta), max(1, int(ttl))

    async def consumir(self, clave: str, maximo: int, ventana_segundos: int) -> Resultado:
        cuenta, ttl = await self._sumar(clave, ventana_segundos)
        if cuenta <= maximo:
            return Resultado(True, ttl)
        return Resultado(False, ttl, recien_bloqueado=cuenta == maximo + 1)

    async def registrar(self, clave: str, ventana_segundos: int) -> None:
        await self._sumar(clave, ventana_segundos)

    async def consultar(self, clave: str, maximo: int) -> Resultado:
        async with self._r.pipeline(transaction=True) as tuberia:
            tuberia.get(clave)
            tuberia.ttl(clave)
            valor, ttl = await tuberia.execute()
        if valor is None or int(valor) < maximo:
            return Resultado(True, 0)
        espera = max(1, int(ttl))
        async with self._r.pipeline(transaction=True) as tuberia:
            tuberia.incr(f"{clave}:rej")
            tuberia.expire(f"{clave}:rej", espera, nx=True)
            rechazos, _ = await tuberia.execute()
        return Resultado(False, espera, recien_bloqueado=int(rechazos) == 1)

    async def reiniciar(self, clave: str) -> None:
        await self._r.delete(clave, f"{clave}:rej")


class LimitadorTolerante:
    """Fail-open (O5): ante un error o un timeout del almacén el pedido pasa y se avisa por log sin IP ni email.

    El aviso se emite como mucho una vez por minuto para no inundar el log mientras el almacén está caído.
    """

    _ultimo_aviso: float = float("-inf")

    def __init__(self, interno: LimitadorSolicitudes, timeout_ms: int, reloj: Callable[[], float] = time.monotonic) -> None:
        self._interno = interno
        self._timeout = timeout_ms / 1000
        self._reloj = reloj

    def _avisar(self, error: BaseException) -> None:
        ahora = self._reloj()
        if ahora - LimitadorTolerante._ultimo_aviso >= 60:
            LimitadorTolerante._ultimo_aviso = ahora
            logger.warning("limite no aplicado: %s", type(error).__name__)

    async def consumir(self, clave: str, maximo: int, ventana_segundos: int) -> Resultado:
        try:
            return await asyncio.wait_for(self._interno.consumir(clave, maximo, ventana_segundos), self._timeout)
        except Exception as error:  # noqa: BLE001 - incluye TimeoutError y los errores del cliente Redis
            self._avisar(error)
            return Resultado(True, 0)

    async def registrar(self, clave: str, ventana_segundos: int) -> None:
        try:
            await asyncio.wait_for(self._interno.registrar(clave, ventana_segundos), self._timeout)
        except Exception as error:  # noqa: BLE001
            self._avisar(error)

    async def consultar(self, clave: str, maximo: int) -> Resultado:
        try:
            return await asyncio.wait_for(self._interno.consultar(clave, maximo), self._timeout)
        except Exception as error:  # noqa: BLE001
            self._avisar(error)
            return Resultado(True, 0)

    async def reiniciar(self, clave: str) -> None:
        try:
            await asyncio.wait_for(self._interno.reiniciar(clave), self._timeout)
        except Exception as error:  # noqa: BLE001
            self._avisar(error)


class LimiteSuperadoError(Exception):
    """Se superó un límite: el handler la convierte en el 429 común (``LimiteSuperadoOut`` + ``Retry-After``)."""

    def __init__(self, reintentar_en_segundos: int) -> None:
        super().__init__("limite superado")
        self.reintentar_en_segundos = reintentar_en_segundos


async def _limite_superado_handler(_: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, LimiteSuperadoError)
    return respuesta_limite_superado(error.reintentar_en_segundos)


def registrar_handlers_limites(app: FastAPI) -> None:
    """Registra el handler del 429 común."""
    app.add_exception_handler(LimiteSuperadoError, _limite_superado_handler)


def get_limitador_base(request: Request) -> LimitadorSolicitudes:
    """Almacén real de contadores (Redis del ``lifespan``). Punto de inyección de los tests (memoria o uno que falla)."""
    cliente = getattr(request.app.state, "redis", None)
    if cliente is None:  # sin lifespan (p. ej. ASGITransport): cliente perezoso que no conecta hasta usarse
        cliente = Redis.from_url(get_settings().redis_url, decode_responses=True)
        request.app.state.redis = cliente
    return LimitadorRedis(cliente)


def get_limitador(base: LimitadorSolicitudes = Depends(get_limitador_base)) -> LimitadorSolicitudes:
    """El limitador con tolerancia a fallas (O5) y timeout (``RATE_LIMIT_TIMEOUT_MS``)."""
    return LimitadorTolerante(base, get_settings().rate_limit_timeout_ms)


def clave_ip(request: Request) -> str:
    """IP del cliente para las claves; ``desconocida`` comparte una ventana común (conservador, D6)."""
    return ip_cliente(request) or "desconocida"


async def _limitar_publico(request: Request, limitador: LimitadorSolicitudes, prefijo: str, maximo: int,
                           ventana: int) -> None:
    resultado = await limitador.consumir(f"rl:v1:pub:{prefijo}:{clave_ip(request)}", maximo, ventana)
    if not resultado.permitido:
        raise LimiteSuperadoError(resultado.reintentar_en_segundos)


async def limitar_publico_escritura(request: Request, limitador: LimitadorSolicitudes = Depends(get_limitador)) -> None:
    """Dependencia de las escrituras públicas (reserva, seña, cancelar, reprogramar, confirmar)."""
    ajustes = get_settings()
    await _limitar_publico(request, limitador, "w", ajustes.rate_limit_publico_escritura_max,
                           ajustes.rate_limit_publico_escritura_ventana_seg)


async def limitar_publico_lectura(request: Request, limitador: LimitadorSolicitudes = Depends(get_limitador)) -> None:
    """Dependencia de las lecturas públicas (catálogo, horarios, consulta de gestión y de seña)."""
    ajustes = get_settings()
    await _limitar_publico(request, limitador, "r", ajustes.rate_limit_publico_lectura_max,
                           ajustes.rate_limit_publico_lectura_ventana_seg)
