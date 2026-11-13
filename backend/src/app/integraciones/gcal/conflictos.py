"""Conflictos entre turnos y Google Calendar (C-10, D6, O9, O18, O20; RN-GC-02).

Un cambio en Google NUNCA modifica un turno: solo se registra un conflicto con el horario del sistema y el de Google, y
una persona lo resuelve con un criterio visible. Los conflictos se cierran solos cuando el turno se cancela o cuando el
desacuerdo desaparece (O20); nada de eso toca ni el turno ni el evento de Google.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integraciones.gcal.errores import AccionNoValidaError, ConflictoCerradoError, ConflictoInexistenteError
from app.integraciones.gcal.models import EventoCalendar, GcalConexion, GcalConflicto
from app.integraciones.gcal.schemas import ConflictoOut
from app.plataforma.auditoria import registrar
from app.shared.settings import get_settings
from app.turnos.models import Profesional, Tratamiento, Turno

ESTADOS_BLOQUEANTES_GCAL = ("reservado", "confirmado")
ACCIONES_POR_TIPO: dict[str, tuple[str, ...]] = {
    "movido_en_google": ("restaurar_en_google", "desvincular"),
    "borrado_en_google": ("restaurar_en_google", "desvincular"),
    "solapa_evento_externo": ("revisado",),
}
CRITERIOS: dict[str, str] = {
    "movido_en_google": "El evento se movió en Google Calendar. El turno sigue en el horario del sistema y no se "
                        "modifica solo: restauralo en Google o desvinculalo.",
    "borrado_en_google": "El evento se borró en Google Calendar. El turno sigue vigente y no se recrea solo: "
                         "restauralo en Google o desvinculalo.",
    "solapa_evento_externo": "El turno se superpone con un evento ocupado de Google Calendar. Nada se cambia solo: "
                             "marcalo como revisado cuando lo hayas resuelto con la profesional.",
}


def _cerrar(conflicto: GcalConflicto, resolucion: str, ahora: datetime, usuario_id: int | None = None) -> None:
    conflicto.estado, conflicto.resolucion = "resuelto", resolucion
    conflicto.resuelto_en, conflicto.resuelto_por_usuario_id = ahora, usuario_id


def _auditar(session: AsyncSession, usuario_id: int | None, conflicto: GcalConflicto, antes: str, resolucion: str) -> None:
    registrar(session, accion="UPDATE", entidad="gcal_conflicto", entidad_id=conflicto.id,  # RN-GL-01: solo ids,
              usuario_id=usuario_id, antes={"estado": antes},  # tipos y estados; ningún dato del paciente
              despues={"estado": "resuelto", "resolucion": resolucion, "tipo": conflicto.tipo,
                       "turno_id": conflicto.turno_id})


async def abrir_conflicto(session: AsyncSession, conexion_id: int, turno: Turno, evento: EventoCalendar, tipo: str,
                          google_inicio: datetime | None, google_fin: datetime | None) -> GcalConflicto | None:
    """Registra el conflicto si no hay uno abierto igual (mismo evento, turno y tipo). Devuelve el nuevo o ``None``."""
    existente = (await session.execute(select(GcalConflicto.id).where(
        GcalConflicto.evento_id == evento.id, GcalConflicto.turno_id == turno.id, GcalConflicto.tipo == tipo,
        GcalConflicto.estado == "abierto"))).first()
    if existente is not None:
        return None
    if tipo == "solapa_evento_externo":  # un "revisado" sobre el mismo desacuerdo no se vuelve a abrir
        revisado = (await session.execute(select(GcalConflicto.id).where(
            GcalConflicto.evento_id == evento.id, GcalConflicto.turno_id == turno.id, GcalConflicto.tipo == tipo,
            GcalConflicto.resolucion == "revisado", GcalConflicto.sistema_inicio == turno.inicio,
            GcalConflicto.sistema_fin == turno.fin, GcalConflicto.google_inicio == google_inicio,
            GcalConflicto.google_fin == google_fin))).first()
        if revisado is not None:
            return None
    conflicto = GcalConflicto(conexion_id=conexion_id, turno_id=turno.id, evento_id=evento.id, tipo=tipo,
                              sistema_inicio=turno.inicio, sistema_fin=turno.fin, google_inicio=google_inicio,
                              google_fin=google_fin)
    session.add(conflicto)
    await session.flush()
    return conflicto


async def sincronizar_conflictos(session: AsyncSession, conexion: GcalConexion, ahora: datetime) -> None:
    """Cierre automático de los conflictos que ya no existen (O20) y alta de los solapes nuevos (D6)."""
    filas = (await session.execute(
        select(GcalConflicto, Turno, EventoCalendar)
        .join(Turno, Turno.id == GcalConflicto.turno_id).join(EventoCalendar, EventoCalendar.id == GcalConflicto.evento_id)
        .where(GcalConflicto.conexion_id == conexion.id, GcalConflicto.estado == "abierto")
        .with_for_update(of=GcalConflicto))).all()
    for conflicto, turno, evento in filas:
        resolucion: str | None = None
        if turno.estado == "cancelado":
            resolucion = "turno_cancelado"
            if conflicto.tipo == "borrado_en_google" and evento.estado in ("pendiente", "sincronizado"):
                evento.estado = "borrado"  # ya no está en Google: no hay nada que borrar
        elif conflicto.tipo == "solapa_evento_externo":
            sigue = (turno.estado in ESTADOS_BLOQUEANTES_GCAL and evento.ocupa and evento.estado != "borrado"
                     and turno.inicio < evento.fin and turno.fin > evento.inicio)
            resolucion = None if sigue else "solape_desaparecido"
        elif conflicto.tipo == "movido_en_google" and (evento.inicio, evento.fin) == (turno.inicio, turno.fin):
            resolucion = "solape_desaparecido"  # la profesional lo devolvió al horario del turno
        if resolucion is not None:
            _cerrar(conflicto, resolucion, ahora)
            _auditar(session, None, conflicto, "abierto", resolucion)
    await session.flush()
    solapes = (await session.execute(
        select(Turno, EventoCalendar)
        .join(EventoCalendar, and_(EventoCalendar.conexion_id == conexion.id, EventoCalendar.origen == "google",
                                   EventoCalendar.ocupa.is_(True), EventoCalendar.estado == "sincronizado",
                                   Turno.inicio < EventoCalendar.fin, Turno.fin > EventoCalendar.inicio))
        .where(Turno.profesional_id == conexion.profesional_id, Turno.estado.in_(ESTADOS_BLOQUEANTES_GCAL),
               Turno.fin > ahora)
        .order_by(Turno.id, EventoCalendar.id))).all()
    for turno, franja in solapes:
        await abrir_conflicto(session, conexion.id, turno, franja, "solapa_evento_externo", franja.inicio, franja.fin)


def _salida(conflicto: GcalConflicto, turno: Turno, profesional: Profesional, tratamiento: str, zona: ZoneInfo,
            puede_resolver: bool) -> ConflictoOut:
    def local(dato: datetime | None) -> datetime | None:
        return None if dato is None else dato.astimezone(zona)

    acciones = list(ACCIONES_POR_TIPO[conflicto.tipo]) if puede_resolver and conflicto.estado == "abierto" else []
    return ConflictoOut(
        id=int(conflicto.id), tipo=conflicto.tipo, estado=conflicto.estado,  # type: ignore[arg-type]
        criterio=CRITERIOS[conflicto.tipo], turno_id=int(turno.id), profesional_id=int(profesional.id),
        profesional_nombre=profesional.nombre, tratamiento=tratamiento, sistema_inicio=local(conflicto.sistema_inicio),  # type: ignore[arg-type]
        sistema_fin=local(conflicto.sistema_fin), google_inicio=local(conflicto.google_inicio),  # type: ignore[arg-type]
        google_fin=local(conflicto.google_fin), acciones=acciones,  # type: ignore[arg-type]
        resolucion=conflicto.resolucion, detectado_en=local(conflicto.detectado_en),  # type: ignore[arg-type]
        resuelto_en=local(conflicto.resuelto_en))


def _consulta_base():  # type: ignore[no-untyped-def]
    return (select(GcalConflicto, Turno, Profesional, Tratamiento.nombre)
            .join(Turno, Turno.id == GcalConflicto.turno_id).join(Profesional, Profesional.id == Turno.profesional_id)
            .join(Tratamiento, Tratamiento.id == Turno.tratamiento_id))


async def listar(session: AsyncSession, estado: str, profesional_id: int | None, *,
                 puede_resolver: bool) -> list[ConflictoOut]:
    """Conflictos del ``estado`` pedido, con las acciones posibles por tipo solo si el usuario puede resolver."""
    consulta = _consulta_base().where(GcalConflicto.estado == estado).order_by(GcalConflicto.id)
    if profesional_id is not None:
        consulta = consulta.where(Turno.profesional_id == profesional_id)
    zona = ZoneInfo(get_settings().app_tz)
    return [_salida(c, t, p, trat, zona, puede_resolver) for c, t, p, trat in (await session.execute(consulta)).all()]


async def resolver(session: AsyncSession, conflicto_id: int, accion: str, usuario_id: int,
                   ahora: datetime) -> ConflictoOut:
    """Resuelve un conflicto abierto con una acción válida para su tipo. Nunca modifica el turno ni escribe en Google."""
    fila = (await session.execute(_consulta_base().where(GcalConflicto.id == conflicto_id)
                                  .with_for_update(of=GcalConflicto))).first()
    if fila is None:
        await session.rollback()
        raise ConflictoInexistenteError()
    conflicto, turno, profesional, tratamiento = fila
    if conflicto.estado != "abierto":
        await session.rollback()
        raise ConflictoCerradoError()
    if turno.estado == "cancelado":  # se canceló entre medio: se cierra solo y no hay nada que resolver
        _cerrar(conflicto, "turno_cancelado", ahora)
        _auditar(session, None, conflicto, "abierto", "turno_cancelado")
        await session.commit()
        raise ConflictoCerradoError()
    if accion not in ACCIONES_POR_TIPO[conflicto.tipo]:
        await session.rollback()
        raise AccionNoValidaError()
    evento = await session.get(EventoCalendar, conflicto.evento_id)
    assert evento is not None
    if accion == "desvincular":
        evento.estado = "desvinculado"
    elif accion == "restaurar_en_google":
        # borrado: el vínculo viejo pasa a historial y el push crea otro con generación + 1; movido: el push lo mueve.
        evento.estado = "borrado" if conflicto.tipo == "borrado_en_google" else "pendiente"
    _cerrar(conflicto, accion, ahora, usuario_id)
    _auditar(session, usuario_id, conflicto, "abierto", accion)
    await session.commit()
    return _salida(conflicto, turno, profesional, tratamiento, ZoneInfo(get_settings().app_tz), True)
