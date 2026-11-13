"""Pull incremental Google -> sistema (C-10, D4, O5, O9, O19).

De un evento AJENO solo se guarda inicio, fin y si ocupa: nunca título, descripción, lugar ni invitados. Un evento del
sistema movido o borrado en Google NUNCA cambia el turno: abre un conflicto (``conflictos.abrir_conflicto``).
"""

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integraciones.gcal.conflictos import ESTADOS_BLOQUEANTES_GCAL, abrir_conflicto
from app.integraciones.gcal.contenido import MARCA_SISTEMA
from app.integraciones.gcal.models import EventoCalendar, GcalConexion
from app.integraciones.gcal.proveedor import EventoGoogle, ProveedorCalendario, SyncTokenVencido
from app.shared.logger import get_logger
from app.shared.settings import Settings
from app.turnos.models import Turno

logger = get_logger(__name__)


def ventana_de_sincronizacion(ahora: datetime, ajustes: Settings) -> tuple[datetime, datetime]:
    """(hoy 00:00 de la clínica, ahora + horizonte), ambos en UTC: el rango de la primera lectura y del push (O6)."""
    zona = ZoneInfo(ajustes.app_tz)
    inicio_del_dia = datetime.combine(ahora.astimezone(zona).date(), time.min, tzinfo=zona).astimezone(timezone.utc)
    return inicio_del_dia, ahora + timedelta(days=ajustes.gcal_horizonte_dias)


async def pull(session: AsyncSession, conexion: GcalConexion, proveedor: ProveedorCalendario, acceso: str,
               ahora: datetime, ajustes: Settings) -> None:
    """Trae los cambios del calendario (incremental con ``syncToken``; completo acotado al horizonte si no hay)."""
    desde, hasta = ventana_de_sincronizacion(ahora, ajustes)
    sync_token = conexion.sync_token
    try:
        cambios = await proveedor.listar(acceso, conexion.calendario_id, sync_token, desde, hasta)
    except SyncTokenVencido:
        sync_token = None
        cambios = await proveedor.listar(acceso, conexion.calendario_id, None, desde, hasta)
    ids = [e.id for e in cambios.eventos]
    vinculos: dict[str, EventoCalendar] = {}
    if ids:
        vinculos = {v.google_event_id: v for v in (await session.execute(select(EventoCalendar).where(
            EventoCalendar.conexion_id == conexion.id, EventoCalendar.google_event_id.in_(ids)))).scalars()}
    for evento in cambios.eventos:
        if evento.propias.get(MARCA_SISTEMA) == "1":
            vinculo = vinculos.get(evento.id)
            if vinculo is not None and vinculo.origen == "sistema":
                await _aplicar_propio(session, conexion, vinculo, evento)
        else:
            _aplicar_ajeno(session, conexion, vinculos.get(evento.id), evento)
    if sync_token is None:  # lectura completa: lo que Google ya no informa deja de ocupar
        visto = set(ids)
        for franja in (await session.execute(select(EventoCalendar).where(
                EventoCalendar.conexion_id == conexion.id, EventoCalendar.origen == "google",
                EventoCalendar.estado == "sincronizado", EventoCalendar.inicio < hasta,
                EventoCalendar.fin > desde))).scalars():
            if franja.google_event_id not in visto:
                franja.estado, franja.ocupa = "borrado", False
    conexion.sync_token = cambios.sync_token
    await session.flush()


def _aplicar_ajeno(session: AsyncSession, conexion: GcalConexion, franja: EventoCalendar | None,
                   evento: EventoGoogle) -> None:
    """Upsert de la franja: solo horario y ocupación (O19). Cancelados y sin horario liberan la franja."""
    if evento.estado == "cancelled" or evento.inicio is None or evento.fin is None or evento.fin <= evento.inicio:
        if franja is not None and franja.origen == "google":
            franja.estado, franja.ocupa = "borrado", False
        return
    if franja is None:
        if evento.ocupa:  # un evento libre que nunca ocupó no hace falta guardarlo
            session.add(EventoCalendar(conexion_id=conexion.id, origen="google", google_event_id=evento.id,
                                       estado="sincronizado", inicio=evento.inicio, fin=evento.fin, ocupa=True,
                                       etag=evento.etag))
        return
    if franja.origen == "google":
        franja.inicio, franja.fin, franja.ocupa = evento.inicio, evento.fin, evento.ocupa
        franja.estado, franja.etag = "sincronizado", evento.etag


async def _aplicar_propio(session: AsyncSession, conexion: GcalConexion, vinculo: EventoCalendar,
                          evento: EventoGoogle) -> None:
    """Evento del sistema: compara su horario con el último conocido; nunca modifica el turno (RN-GC-02, O9)."""
    if vinculo.estado not in ("pendiente", "sincronizado"):
        return
    turno = await session.get(Turno, vinculo.turno_id)
    if turno is None:
        return
    bloquea = turno.estado in ESTADOS_BLOQUEANTES_GCAL
    if evento.estado == "cancelled":
        if bloquea:
            await abrir_conflicto(session, conexion.id, turno, vinculo, "borrado_en_google", None, None)
        elif turno.estado == "cancelado":
            vinculo.estado = "borrado"  # ya no está en Google: no hay nada que borrar
        return
    vinculo.etag = evento.etag  # un cambio de solo texto no es conflicto, pero el push necesita el etag vigente
    if evento.inicio is None or evento.fin is None or (evento.inicio, evento.fin) == (vinculo.inicio, vinculo.fin):
        return
    if (evento.inicio, evento.fin) == (turno.inicio, turno.fin):
        vinculo.inicio, vinculo.fin = evento.inicio, evento.fin  # Google coincide con el turno actual
    elif bloquea:
        vinculo.inicio, vinculo.fin = evento.inicio, evento.fin  # horario conocido en Google (O9)
        await abrir_conflicto(session, conexion.id, turno, vinculo, "movido_en_google", evento.inicio, evento.fin)
