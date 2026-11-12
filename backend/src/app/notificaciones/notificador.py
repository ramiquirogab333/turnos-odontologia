"""Implementación de ``NotificadorTurnos`` para los recordatorios (C-09, D6, O8).

Al cancelar o reprogramar un turno, anula los recordatorios vigentes del HORARIO ANTERIOR con una sola ``UPDATE`` liviana
en una sesión propia, después del commit del turno. Si falla, ``publicar_sin_romper`` lo loguea y el ciclo del trabajo
(``service._reconciliar``) lo corrige en el siguiente intervalo: el estado del turno es la fuente de verdad (C-07 O8).
"""

from collections.abc import Sequence

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.gestion.eventos import EventoTurno, NotificadorTurnos
from app.notificaciones.models import Recordatorio
from app.notificaciones.service import ESTADOS_ANULABLES


class NotificadorRecordatorios:
    """Anula los recordatorios del horario anterior del turno."""

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    async def publicar(self, evento: EventoTurno) -> None:
        async with self._factory() as session:
            await session.execute(
                update(Recordatorio)
                .where(Recordatorio.turno_id == evento.turno_id, Recordatorio.turno_inicio == evento.inicio_anterior,
                       Recordatorio.estado.in_(ESTADOS_ANULABLES))
                .values(estado="anulado", motivo=evento.tipo, confirmado_en=None, proximo_intento_en=None)
                .execution_options(synchronize_session=False))
            await session.commit()


class NotificadorCompuesto:
    """Reparte el evento a varios consumidores (hoy recordatorios; C-10 suma Google Calendar).

    Todos reciben el evento aunque alguno falle; si hubo fallas se relanza la primera para que el publicador externo
    la registre sin revertir la operación del paciente.
    """

    def __init__(self, notificadores: Sequence[NotificadorTurnos]) -> None:
        self._notificadores = list(notificadores)

    async def publicar(self, evento: EventoTurno) -> None:
        errores: list[Exception] = []
        for notificador in self._notificadores:
            try:
                await notificador.publicar(evento)
            except Exception as error:  # noqa: BLE001 - un consumidor caído no debe privar a los demás del evento
                errores.append(error)
        if errores:
            raise errores[0]
