"""``NotificadorTurnos`` de Google Calendar (C-10, D7, O4): la API nunca llama a Google (R16).

Al cancelar o reprogramar un turno solo MARCA el vínculo del evento como ``pendiente`` y limpia la espera de la conexión,
con una ``UPDATE`` liviana en una sesión propia después del commit del turno. El trabajo ``gcal_sync`` hace las llamadas.
Si esto falla, ``publicar_sin_romper`` lo loguea y el diff de la reconciliación lo corrige igual: el estado del turno manda.
"""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.gestion.eventos import EventoTurno
from app.integraciones.gcal.models import EventoCalendar, GcalConexion


class NotificadorCalendario:
    """Marca el evento del turno como pendiente de sincronizar; no toca la red."""

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    async def publicar(self, evento: EventoTurno) -> None:
        async with self._factory() as session:
            conexiones = select(GcalConexion.id).where(GcalConexion.profesional_id == evento.profesional_id,
                                                       GcalConexion.estado == "activa")
            await session.execute(
                update(EventoCalendar)
                .where(EventoCalendar.turno_id == evento.turno_id, EventoCalendar.origen == "sistema",
                       EventoCalendar.estado == "sincronizado", EventoCalendar.conexion_id.in_(conexiones))
                .values(estado="pendiente").execution_options(synchronize_session=False))
            await session.execute(
                update(GcalConexion)
                .where(GcalConexion.profesional_id == evento.profesional_id, GcalConexion.estado == "activa")
                .values(proximo_intento_en=None).execution_options(synchronize_session=False))
            await session.commit()
