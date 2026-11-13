"""Franjas ocupadas de Google Calendar en la disponibilidad (C-10, D8, O10, O19): una sola consulta por operación.

Cuentan como ocupación de la PROFESIONAL (nunca de un sillón) las franjas ``origen = google`` que ocupan, de conexiones
``activa`` o ``revocada`` (una ``desconectada`` o ``pendiente`` ya no las excluye). No son turnos: no entran al EXCLUDE de
la base (R5) y el 409 que producen no revela que el motivo es Google.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integraciones.gcal.models import EventoCalendar, GcalConexion, GcalConflicto

ESTADOS_CONEXION_QUE_EXCLUYEN = ("activa", "revocada")


@dataclass(frozen=True)
class FranjaOcupada:
    profesional_id: int
    inicio: datetime
    fin: datetime


async def franjas_ocupadas(session: AsyncSession, desde: datetime, hasta: datetime,
                           profesional_id: int | None = None,
                           profesionales_ids: list[int] | None = None) -> list[FranjaOcupada]:
    """Franjas ocupadas que rozan ``[desde, hasta)``, opcionalmente de una o varias profesionales."""
    consulta = (select(GcalConexion.profesional_id, EventoCalendar.inicio, EventoCalendar.fin)
                .join(GcalConexion, GcalConexion.id == EventoCalendar.conexion_id)
                .where(EventoCalendar.origen == "google", EventoCalendar.ocupa.is_(True),
                       GcalConexion.estado.in_(ESTADOS_CONEXION_QUE_EXCLUYEN),
                       EventoCalendar.inicio < hasta, EventoCalendar.fin > desde)
                .order_by(EventoCalendar.inicio, EventoCalendar.id))
    if profesional_id is not None:
        consulta = consulta.where(GcalConexion.profesional_id == profesional_id)
    if profesionales_ids is not None:
        consulta = consulta.where(GcalConexion.profesional_id.in_(profesionales_ids))
    return [FranjaOcupada(int(p), i, f) for p, i, f in (await session.execute(consulta)).all()]


async def calendario_de_turnos(session: AsyncSession, turno_ids: list[int]) -> dict[int, tuple[str, bool]]:
    """``{turno_id: (estado del evento, tiene conflicto abierto)}``; lo que no aparece es ``sin_evento`` sin conflicto.

    Dos consultas para toda la agenda (sin N+1). Solo cuentan los vínculos del sistema pendientes, sincronizados o
    desvinculados; un vínculo ``borrado`` es historial.
    """
    if not turno_ids:
        return {}
    estados = {int(t): str(e) for t, e in (await session.execute(
        select(EventoCalendar.turno_id, EventoCalendar.estado).where(
            EventoCalendar.turno_id.in_(turno_ids), EventoCalendar.origen == "sistema",
            EventoCalendar.estado.in_(("pendiente", "sincronizado", "desvinculado"))))).all()}
    con_conflicto = {int(t) for t in (await session.execute(
        select(GcalConflicto.turno_id).where(GcalConflicto.turno_id.in_(turno_ids),
                                             GcalConflicto.estado == "abierto"))).scalars()}
    return {t: (estados.get(t, "sin_evento"), t in con_conflicto) for t in set(estados) | con_conflicto}
