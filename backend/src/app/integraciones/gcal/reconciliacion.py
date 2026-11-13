"""Push sistema -> Google por reconciliación (C-10, D5, O4, O6, O7, O9, O17).

El estado del turno es la fuente de verdad: cada ciclo compara los turnos con sus vínculos ``evento_calendar`` y escribe
solo las diferencias, así que perder un aviso nunca deja Google mal de forma permanente. Idempotente: el id del evento
es determinista (turno, conexión, generación) y un ``409`` significa "ya existe", no un error. Nunca sobrescribe un
evento con conflicto abierto o desvinculado (RN-GC-02).
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integraciones.gcal.conflictos import ESTADOS_BLOQUEANTES_GCAL, abrir_conflicto
from app.integraciones.gcal.contenido import ContenidoEvento, armar_contenido, hash_contenido, id_evento
from app.integraciones.gcal.models import EventoCalendar, GcalConexion, GcalConflicto
from app.integraciones.gcal.proveedor import (EtagDesactualizado, EventoDuplicado, EventoGoogle, EventoInexistente,
                                              ProveedorCalendario)
from app.integraciones.gcal.pull import ventana_de_sincronizacion
from app.shared.logger import get_logger
from app.shared.settings import Settings
from app.turnos.models import Sillon, Tratamiento, Turno

logger = get_logger(__name__)
MAX_GENERACIONES_POR_CICLO = 3  # ids de eventos borrados que Google no reutiliza


async def reconciliar_push(session: AsyncSession, conexion: GcalConexion, proveedor: ProveedorCalendario, acceso: str,
                           ahora: datetime, ajustes: Settings) -> None:
    """Crea, mueve o borra los eventos de la conexión para que coincidan con el estado actual de los turnos."""
    desde, hasta = ventana_de_sincronizacion(ahora, ajustes)
    zona = ZoneInfo(ajustes.app_tz)
    vinculos: dict[int, list[EventoCalendar]] = {}
    for vinculo in (await session.execute(select(EventoCalendar).where(
            EventoCalendar.conexion_id == conexion.id, EventoCalendar.origen == "sistema")
            .order_by(EventoCalendar.generacion))).scalars():
        vinculos.setdefault(int(vinculo.turno_id), []).append(vinculo)  # type: ignore[arg-type]
    con_vigente = [tid for tid, lista in vinculos.items() if any(v.estado in ("pendiente", "sincronizado") for v in lista)]
    filas = (await session.execute(
        select(Turno, Tratamiento.nombre, Sillon.nombre)
        .join(Tratamiento, Tratamiento.id == Turno.tratamiento_id).join(Sillon, Sillon.id == Turno.sillon_id)
        .where(Turno.profesional_id == conexion.profesional_id,
               or_(Turno.id.in_(con_vigente),
                   (Turno.estado.in_(ESTADOS_BLOQUEANTES_GCAL) & (Turno.inicio >= desde) & (Turno.inicio < hasta))))
        .order_by(Turno.inicio, Turno.id))).all()
    abiertos = {int(c) for c in (await session.execute(select(GcalConflicto.turno_id).where(
        GcalConflicto.conexion_id == conexion.id, GcalConflicto.estado == "abierto",
        GcalConflicto.tipo.in_(("movido_en_google", "borrado_en_google"))))).scalars()}
    for turno, tratamiento, sillon in filas:
        lista = vinculos.get(int(turno.id), [])
        if any(v.estado == "desvinculado" for v in lista):
            continue  # la resolución manual manda: el sistema no vuelve a tocar ese evento
        vigente = next((v for v in lista if v.estado in ("pendiente", "sincronizado")), None)
        bloquea = turno.estado in ESTADOS_BLOQUEANTES_GCAL
        contenido = armar_contenido(turno_id=turno.id, tratamiento=tratamiento, sillon=sillon, inicio=turno.inicio,
                                    fin=turno.fin, zona=zona, url_panel=ajustes.public_panel_url.rstrip("/"))
        if vigente is None:
            if bloquea:
                generacion = max((v.generacion for v in lista), default=-1) + 1
                await _crear(session, conexion, proveedor, acceso, turno, contenido, generacion)
            continue
        if turno.id in abiertos:
            continue  # conflicto abierto: nunca se sobrescribe (RN-GC-02)
        if turno.estado == "cancelado":
            await _borrar(conexion, proveedor, acceso, vigente)
        elif bloquea and (vigente.estado == "pendiente" or vigente.hash_contenido != hash_contenido(contenido)
                          or (vigente.inicio, vigente.fin) != (turno.inicio, turno.fin)):
            await _actualizar(session, conexion, proveedor, acceso, turno, vigente, contenido)
        # ausente / atendido / en_espera: el evento se conserva sin cambios (O7)
    await session.flush()


async def _crear(session: AsyncSession, conexion: GcalConexion, proveedor: ProveedorCalendario, acceso: str,
                 turno: Turno, contenido: ContenidoEvento, generacion: int) -> None:
    adoptado: EventoGoogle | None = None
    creado: EventoGoogle | None = None
    for _ in range(MAX_GENERACIONES_POR_CICLO):
        evento_id = id_evento(turno.id, conexion.id, generacion)
        try:
            creado = await proveedor.insertar(acceso, conexion.calendario_id, evento_id, contenido)
            break
        except EventoDuplicado:
            existente = await proveedor.obtener(acceso, conexion.calendario_id, evento_id)
            if existente is not None and existente.estado != "cancelled":
                adoptado = existente  # un ciclo anterior ya lo creó y no llegó a guardar el vínculo
                break
            generacion += 1  # Google no reutiliza el id de un evento borrado
    origen = creado or adoptado
    if origen is None:
        return
    vinculo = EventoCalendar(
        conexion_id=conexion.id, turno_id=turno.id, origen="sistema", google_event_id=origen.id, estado="sincronizado",
        inicio=turno.inicio if creado else (origen.inicio or turno.inicio),
        fin=turno.fin if creado else (origen.fin or turno.fin), ocupa=True, etag=origen.etag,
        hash_contenido=hash_contenido(contenido) if creado else None, generacion=generacion)
    session.add(vinculo)
    await session.flush()
    if adoptado is not None:  # se alinea con el contenido actual del turno en este mismo ciclo
        await _actualizar(session, conexion, proveedor, acceso, turno, vinculo, contenido)


async def _actualizar(session: AsyncSession, conexion: GcalConexion, proveedor: ProveedorCalendario, acceso: str,
                      turno: Turno, vinculo: EventoCalendar, contenido: ContenidoEvento) -> None:
    try:
        actualizado = await proveedor.actualizar(acceso, conexion.calendario_id, vinculo.google_event_id, contenido,
                                                 vinculo.etag or "")
    except EtagDesactualizado:
        logger.info("gcal: el evento cambió en Google; no se escribe y el pull del ciclo siguiente decide")
        return
    except EventoInexistente:  # se borró en Google sin que el pull lo viera todavía
        await abrir_conflicto(session, conexion.id, turno, vinculo, "borrado_en_google", None, None)
        return
    vinculo.etag, vinculo.hash_contenido, vinculo.estado = actualizado.etag, hash_contenido(contenido), "sincronizado"
    vinculo.inicio, vinculo.fin = turno.inicio, turno.fin


async def _borrar(conexion: GcalConexion, proveedor: ProveedorCalendario, acceso: str, vinculo: EventoCalendar) -> None:
    try:
        await proveedor.borrar(acceso, conexion.calendario_id, vinculo.google_event_id)
    except EventoInexistente:
        pass  # ya no estaba: el resultado es el mismo
    vinculo.estado = "borrado"
