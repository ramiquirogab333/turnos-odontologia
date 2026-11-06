"""Puerto de eventos de cancelación y reprogramación (C-07, D5).

C-09 (recordatorios) y C-10 (Google Calendar) implementan ``NotificadorTurnos``. El evento NUNCA lleva nombre,
teléfono ni código de gestión (R19, Ley 25.326): los consumidores resuelven lo que necesiten por ``turno_id``.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from app.shared.logger import get_logger

logger = get_logger(__name__)

TipoEvento = Literal["turno_cancelado", "turno_reprogramado"]


@dataclass(frozen=True)
class EventoTurno:
    """Hecho ya confirmado en la base (se publica después del commit)."""

    tipo: TipoEvento
    turno_id: int
    profesional_id: int
    inicio_anterior: datetime
    fin_anterior: datetime
    inicio_nuevo: datetime | None
    fin_nuevo: datetime | None
    ocurrido_en: datetime


class NotificadorTurnos(Protocol):
    """Quien reacciona a un turno cancelado o movido (calendario, recordatorios)."""

    async def publicar(self, evento: EventoTurno) -> None: ...


class NotificadorNulo:
    """Implementación v1: solo deja un log estructurado sin datos personales."""

    async def publicar(self, evento: EventoTurno) -> None:
        logger.info("evento_turno tipo=%s turno_id=%d", evento.tipo, evento.turno_id)
