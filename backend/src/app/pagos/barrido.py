"""Barrido de pre-reservas vencidas (D8). Idempotente; C-09 lo moverá a su scheduler sin cambiar el servicio.

``expirar_pre_reservas`` pasa a ``cancelado`` los ``en_espera`` con ``en_espera_vence_en <= ahora`` y a
``vencido`` sus pagos pendientes, con una auditoría por turno (RN-SN-07). No genera ``acreditacion_sena``:
un turno que vence sin pagar no dispara recordatorios ni eventos (RN-SN-01, RN-WA-03). Es I/O asíncrono
liviano: no bloquea el event loop (R16).
"""

import asyncio
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.core import RegistroAuditoria
from app.pagos.models import PagoSena
from app.public.service import LOCK_RESERVAS
from app.shared.logger import get_logger
from app.turnos.models import Turno

logger = get_logger(__name__)


async def expirar_pre_reservas(session: AsyncSession, ahora: datetime) -> int:
    """Cancela las pre-reservas vencidas a ``ahora``. Devuelve cuántos turnos pasó a ``cancelado``.

    Mismo orden de locks que el resto del módulo: advisory de reservas -> turno -> pago_sena (hallazgo 4).
    """
    await session.execute(select(func.pg_advisory_xact_lock(LOCK_RESERVAS)))
    vencidos = (await session.execute(
        select(Turno).where(Turno.estado == "en_espera", Turno.en_espera_vence_en <= ahora)
        .with_for_update(skip_locked=True)  # si una acreditación está en curso, esa fila se salta
        .execution_options(populate_existing=True)
    )).scalars().all()
    for turno in vencidos:
        for pago in (await session.execute(
                select(PagoSena).where(PagoSena.turno_id == turno.id, PagoSena.estado == "pendiente")
                .with_for_update())).scalars().all():
            pago.estado = "vencido"
        vence = turno.en_espera_vence_en
        turno.estado = "cancelado"
        session.add(RegistroAuditoria(
            usuario_id=None, accion="UPDATE", entidad="turno", entidad_id=str(turno.id),
            datos_antes={"estado": "en_espera", "en_espera_vence_en": vence.isoformat() if vence else None},
            datos_despues={"estado": "cancelado", "origen": "vencimiento_sena"}, ip=None))
    await session.commit()
    return len(vencidos)


async def ciclo_barrido(factory: async_sessionmaker[AsyncSession], intervalo_segundos: int) -> None:
    """Tarea del ``lifespan``: barre cada ``intervalo_segundos`` hasta que la cancelen al apagar la app."""
    while True:
        try:
            async with factory() as session:
                cancelados = await expirar_pre_reservas(session, datetime.now(timezone.utc))
            if cancelados:
                logger.info("barrido de señas: %s pre-reservas vencidas", cancelados)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - un fallo puntual no debe matar la tarea periódica
            logger.exception("barrido de señas: error; se reintenta en el próximo ciclo")
        await asyncio.sleep(intervalo_segundos)
