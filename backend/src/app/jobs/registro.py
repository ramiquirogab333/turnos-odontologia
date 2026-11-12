"""Registro de trabajos periódicos (C-09, D1). Registrar un trabajo nuevo = una función ``(session, ahora)`` + un intervalo.

Cada trabajo es una función idempotente y pura respecto del reloj (testeable con Postgres y sin Redis). El adaptador
``ejecutar_trabajo`` abre la sesión, inyecta ``ahora`` con zona y nunca deja caer al worker: una excepción se
loguea sin datos personales (solo el nombre del trabajo y la clase del error, R19) y el siguiente ciclo corre normal.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.notificaciones.proveedor import obtener_proveedor
from app.notificaciones.service import generar_recordatorios
from app.pagos.barrido import expirar_pre_reservas
from app.shared.logger import get_logger
from app.shared.settings import Settings

logger = get_logger(__name__)

FuncionTrabajo = Callable[[AsyncSession, datetime], Awaitable[int]]


@dataclass(frozen=True)
class TrabajoProgramado:
    """Un trabajo periódico: nombre estable, cada cuántos segundos corre y qué ejecuta."""

    nombre: str
    intervalo_segundos: int
    funcion: FuncionTrabajo


def trabajos_programados(ajustes: Settings) -> list[TrabajoProgramado]:
    """Los trabajos habilitados por la configuración (cada uno se puede apagar por variable de entorno)."""
    trabajos: list[TrabajoProgramado] = []
    if ajustes.recordatorios_habilitado:
        anticipacion = ajustes.anticipacion_recordatorio

        async def recordatorios(session: AsyncSession, ahora: datetime) -> int:
            resumen = await generar_recordatorios(session, ahora, anticipacion, obtener_proveedor())
            return resumen.generados

        trabajos.append(TrabajoProgramado("recordatorios", ajustes.recordatorios_intervalo_segundos, recordatorios))
    if ajustes.sena_barrido_habilitado:
        async def barrido_sena(session: AsyncSession, ahora: datetime) -> int:
            cancelados = await expirar_pre_reservas(session, ahora)
            if cancelados:
                logger.info("barrido de señas: %d pre-reservas vencidas", cancelados)
            return cancelados

        trabajos.append(TrabajoProgramado("barrido_sena", ajustes.sena_barrido_segundos, barrido_sena))
    return trabajos


async def ejecutar_trabajo(trabajo: TrabajoProgramado, factory: async_sessionmaker[AsyncSession]) -> int | None:
    """Corre un ciclo del trabajo. Devuelve su resultado, o ``None`` si falló (el error queda en el log sin PII)."""
    try:
        async with factory() as session:
            return await trabajo.funcion(session, datetime.now(timezone.utc))
    except Exception as error:  # noqa: BLE001 - un ciclo fallido no debe detener al worker ni a los otros trabajos
        logger.error("trabajo %s: ciclo fallido (%s); se reintenta en el próximo intervalo", trabajo.nombre,
                     type(error).__name__)
        return None
