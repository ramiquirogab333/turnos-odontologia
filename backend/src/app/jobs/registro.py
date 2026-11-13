"""Registro de trabajos periódicos (C-09, D1). Registrar un trabajo nuevo = una función ``(session, ahora)`` + un intervalo.

Cada trabajo es una función idempotente y pura respecto del reloj (testeable con Postgres y sin Redis). El adaptador
``ejecutar_trabajo`` abre la sesión, inyecta ``ahora`` con zona y nunca deja caer al worker: una excepción se
loguea sin datos personales (solo el nombre del trabajo y la clase del error, R19) y el siguiente ciclo corre normal.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integraciones.gcal.proveedor import ProveedorCalendario
from app.integraciones.gcal.proveedor_http import ProveedorHttp
from app.integraciones.gcal.sincronizacion import sincronizar_calendarios

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


def trabajos_programados(ajustes: Settings, proveedor_gcal: ProveedorCalendario | None = None) -> list[TrabajoProgramado]:
    """Los trabajos habilitados por la configuración (cada uno se puede apagar por variable de entorno).

    ``gcal_sync`` (C-10) solo se registra con ``GCAL_SYNC_HABILITADO`` y credenciales de Google; sin ellas el worker
    arranca igual, avisa sin mostrar ningún secreto y los demás trabajos corren normal.
    """
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
    if ajustes.gcal_sync_habilitado:
        if ajustes.gcal_configurado:
            proveedor = proveedor_gcal or ProveedorHttp.desde_ajustes(ajustes)

            async def gcal_sync(session: AsyncSession, ahora: datetime) -> int:
                # Cada conexión usa su propia sesión y transacción (lock por conexión): se abren sobre el mismo motor.
                factory = async_sessionmaker(session.bind, expire_on_commit=False)
                return await sincronizar_calendarios(factory, proveedor, ahora, ajustes)

            trabajos.append(TrabajoProgramado("gcal_sync", ajustes.gcal_sync_intervalo_segundos, gcal_sync))
        else:
            logger.warning("trabajo gcal_sync no registrado: faltan credenciales de Google Calendar "
                           "(GCAL_CLIENT_ID, GCAL_CLIENT_SECRET, GCAL_TOKEN_CLAVE)")
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
