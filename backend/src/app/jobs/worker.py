"""Worker de trabajos programados sobre arq + Redis (C-09, D1, O1).

Arranque: ``arq app.jobs.worker.WorkerSettings`` (healthcheck: ``arq --check app.jobs.worker.WorkerSettings``).
El dominio no depende de arq: los trabajos son funciones ``(session, ahora)`` del registro; cambiar de librería toca
solo este archivo. arq deduplica cada ejecución cron por su ranura de tiempo (``unique=True``), así que dos workers no
repiten el mismo ciclo; además cada trabajo es idempotente por sí mismo.
"""

from typing import Any

from arq import cron
from arq.connections import RedisSettings
from arq.cron import CronJob

from app.jobs.registro import TrabajoProgramado, ejecutar_trabajo, trabajos_programados
from app.shared.db import get_engine, get_session_factory
from app.shared.logger import get_logger
from app.shared.settings import get_settings

logger = get_logger(__name__)

HEALTH_CHECK_SEGUNDOS = 30
ESPERA_APAGADO_SEGUNDOS = 20  # un ciclo en curso termina (commit completo) antes de detener el worker


def _divisor_mas_cercano_hacia_abajo(valor: int, base: int) -> int:
    """Mayor divisor de ``base`` que no supera ``valor`` (cron solo expresa intervalos que dividen la unidad)."""
    return max(d for d in range(1, base + 1) if base % d == 0 and d <= max(valor, 1))


def especificacion_cron(intervalo_segundos: int) -> dict[str, Any]:
    """Traduce un intervalo a campos cron de arq. Si no divide la unidad, baja al divisor más cercano."""
    if intervalo_segundos < 60:
        paso = _divisor_mas_cercano_hacia_abajo(intervalo_segundos, 60)
        return {"second": set(range(0, 60, paso))}
    if intervalo_segundos < 3600:
        paso = _divisor_mas_cercano_hacia_abajo(intervalo_segundos // 60, 60)
        return {"minute": set(range(0, 60, paso)), "second": 0}
    paso = _divisor_mas_cercano_hacia_abajo(intervalo_segundos // 3600, 24)
    return {"hour": set(range(0, 24, paso)), "minute": 0, "second": 0}


def construir_cron(trabajos: list[TrabajoProgramado]) -> list[CronJob]:
    """Un cron de arq por trabajo; el adaptador toma la fábrica de sesiones del contexto del worker."""
    crones: list[CronJob] = []
    for trabajo in trabajos:
        async def ciclo(ctx: dict[str, Any], _trabajo: TrabajoProgramado = trabajo) -> int | None:
            return await ejecutar_trabajo(_trabajo, ctx["factory"])

        ciclo.__name__ = trabajo.nombre
        crones.append(cron(ciclo, name=trabajo.nombre, timeout=300, **especificacion_cron(trabajo.intervalo_segundos)))
    return crones


async def iniciar(ctx: dict[str, Any]) -> None:
    ctx["factory"] = get_session_factory()
    for trabajo in _TRABAJOS:
        logger.info("worker: trabajo programado %s cada %ds", trabajo.nombre, trabajo.intervalo_segundos)


async def apagar(ctx: dict[str, Any]) -> None:
    await get_engine().dispose()


_AJUSTES = get_settings()
_TRABAJOS = trabajos_programados(_AJUSTES)


class WorkerSettings:
    """Configuración que lee ``arq``: sin secretos en el código (R17), todo viene del entorno."""

    functions: list[Any] = []
    cron_jobs = construir_cron(_TRABAJOS)
    redis_settings = RedisSettings.from_dsn(_AJUSTES.redis_url)
    on_startup = iniciar
    on_shutdown = apagar
    health_check_interval = HEALTH_CHECK_SEGUNDOS
    job_completion_wait = ESPERA_APAGADO_SEGUNDOS
    max_jobs = 4
