"""Servicio del panel interno: agenda por rol (C-08, D2). Todo el I/O es asíncrono (R16)."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, not_, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import PermissionContext
from app.gestion.errores import FueraDePlazoError
from app.gestion.eventos import EventoTurno, NotificadorTurnos
from app.gestion.service import ESTADOS_GESTIONABLES, publicar_sin_romper
from app.models.core import RegistroAuditoria, Usuario
from app.pagos.estados import (
    CancelacionFueraDePlazoError,
    atendido_habilitado_desde,
    ausente_habilitado_desde,
    limite_cambios,
)
from app.pagos.models import PagoSena
from app.pagos.service import ResultadoCambioEstado, cambiar_estado_turno
from app.panel.acciones import Permiso, acciones_permitidas
from app.integraciones.gcal.disponibilidad import calendario_de_turnos, franjas_ocupadas
from app.panel.schemas import (
    AgendaQuery,
    AgendaResponse,
    CalendarioTurno,
    OcupadoGoogle,
    OpcionesResponse,
    Ref,
    SenaAgenda,
    TratamientoRef,
    TurnoAgenda,
    TurnoManualCreado,
    TurnoManualCreate,
)
from app.public.service import (
    LOCK_RESERVAS,
    SQLSTATE_DEADLOCK,
    SQLSTATE_EXCLUSION,
    FueraDeDisponibilidadError,
    ReservaConflictoError,
    _alternativas,
    _cargar_bloqueos,
    _franja_que_contiene,
    _profesional_ocupado,
    _sillon_libre,
    _sillones_activos,
)
from app.shared.exceptions import ReferenceNotFoundError
from app.shared.settings import get_settings
from app.turnos.models import Profesional, Sillon, Tratamiento, Turno
from app.turnos.service import ESTADOS_BLOQUEANTES, motivo_desde_mensaje


class SinAccesoAlPanelError(Exception):
    """El usuario no tiene ninguno de los roles del panel (403)."""

    def __init__(self) -> None:
        super().__init__("No tenés permisos para usar el panel")


class SinProfesionalAsociadoError(Exception):
    """Un odontólogo sin profesional asociado no tiene agenda que ver (403 ``sin_profesional_asociado``)."""

    def __init__(self) -> None:
        super().__init__("Tu usuario todavía no está asociado a un profesional. Pedile a la clínica que lo asocie.")


class AgendaAjenaError(Exception):
    """Un odontólogo pidió la agenda de otro profesional (403 ``agenda_ajena``)."""

    def __init__(self) -> None:
        super().__init__("Solo podés ver tu propia agenda")


@dataclass(frozen=True)
class Alcance:
    """Qué puede ver y hacer quien consulta. ``profesional_id`` restringe la agenda a esa profesional (O5, O6)."""

    puede_escribir: bool
    profesional_id: int | None
    marca_atendido: bool = False  # C-11 O15: la odontóloga marca ``atendido`` sus turnos (no escribe nada más)


def zona_clinica() -> ZoneInfo:
    return ZoneInfo(get_settings().app_tz)


def tolerancia_ausente() -> timedelta:
    return timedelta(minutes=get_settings().ausente_tolerancia_minutos)


async def resolver_alcance(session: AsyncSession, contexto: PermissionContext) -> Alcance:
    """El permiso más amplio gana: recepción y admin ven todo y escriben; un odontólogo puro ve solo lo suyo."""
    if contexto.tiene_rol("recepcion") or contexto.tiene_rol("admin"):
        return Alcance(puede_escribir=True, profesional_id=None, marca_atendido=True)
    if not contexto.tiene_rol("odontologo"):
        raise SinAccesoAlPanelError()
    profesional_id = (await session.execute(
        select(Usuario.profesional_id).where(Usuario.id == contexto.usuario_id))).scalar_one_or_none()
    if profesional_id is None:
        raise SinProfesionalAsociadoError()
    return Alcance(puede_escribir=False, profesional_id=int(profesional_id), marca_atendido=True)


def rango_utc(vista: str, fecha: date, zona: ZoneInfo) -> tuple[date, date, datetime, datetime]:
    """(primer día, último día, desde UTC, hasta UTC exclusivo): el período se mide en la hora de la clínica."""
    primero = fecha if vista == "dia" else fecha - timedelta(days=fecha.weekday())
    ultimo = primero if vista == "dia" else primero + timedelta(days=6)
    desde = datetime.combine(primero, time.min, tzinfo=zona).astimezone(timezone.utc)
    hasta = datetime.combine(ultimo + timedelta(days=1), time.min, tzinfo=zona).astimezone(timezone.utc)
    return primero, ultimo, desde, hasta


async def consultar_agenda(session: AsyncSession, alcance: Alcance, query: AgendaQuery,
                           ahora: datetime) -> AgendaResponse:
    """Agenda del período en UNA consulta con joins (sin N+1). Un turno pertenece al día en que empieza."""
    if alcance.profesional_id is not None and query.profesional_id not in (None, alcance.profesional_id):
        raise AgendaAjenaError()
    if query.profesional_id is not None and await session.get(Profesional, query.profesional_id) is None:
        raise ReferenceNotFoundError(campo="profesional_id")
    if query.sillon_id is not None and await session.get(Sillon, query.sillon_id) is None:
        raise ReferenceNotFoundError(campo="sillon_id")

    zona = zona_clinica()
    primero, ultimo, desde, hasta = rango_utc(query.vista, query.fecha, zona)
    en_periodo = and_(Turno.inicio >= desde, Turno.inicio < hasta)
    ultimo_pago = (
        select(PagoSena.turno_id.label("turno_id"), func.max(PagoSena.id).label("pago_id"))
        .where(PagoSena.turno_id.in_(select(Turno.id).where(en_periodo)))
        .group_by(PagoSena.turno_id).subquery()
    )
    consulta = (
        select(Turno, Profesional.nombre, Sillon.nombre, Tratamiento.nombre, Tratamiento.duracion_minutos,
               PagoSena.estado, PagoSena.monto)
        .join(Profesional, Profesional.id == Turno.profesional_id)
        .join(Sillon, Sillon.id == Turno.sillon_id)
        .join(Tratamiento, Tratamiento.id == Turno.tratamiento_id)
        .outerjoin(ultimo_pago, ultimo_pago.c.turno_id == Turno.id)
        .outerjoin(PagoSena, PagoSena.id == ultimo_pago.c.pago_id)
        .where(en_periodo, Turno.estado != "cancelado",
               not_(and_(Turno.estado == "en_espera", Turno.en_espera_vence_en <= ahora)))
        .order_by(Turno.inicio, Turno.id)
    )
    profesional_filtro = alcance.profesional_id if alcance.profesional_id is not None else query.profesional_id
    if profesional_filtro is not None:
        consulta = consulta.where(Turno.profesional_id == profesional_filtro)
    if query.sillon_id is not None:
        consulta = consulta.where(Turno.sillon_id == query.sillon_id)

    tolerancia = tolerancia_ausente()
    permiso: Permiso = ("total" if alcance.puede_escribir else "solo_atendido" if alcance.marca_atendido
                        else "ninguno")
    turnos: list[TurnoAgenda] = []
    for turno, profesional, sillon, tratamiento, duracion, estado_pago, monto_pago in (
            await session.execute(consulta)).all():
        turnos.append(TurnoAgenda(
            id=int(turno.id), inicio=turno.inicio.astimezone(zona), fin=turno.fin.astimezone(zona),
            estado=turno.estado, bloquea_agenda=turno.estado in ESTADOS_BLOQUEANTES, origen=turno.origen,
            profesional=Ref(id=turno.profesional_id, nombre=profesional),
            sillon=Ref(id=turno.sillon_id, nombre=sillon),
            tratamiento=TratamientoRef(id=turno.tratamiento_id, nombre=tratamiento, duracion_minutos=duracion),
            paciente_nombre=turno.contacto_nombre,
            # O6: el teléfono es dato de contacto operativo; la odontóloga no lo recibe. Nunca el código de gestión.
            paciente_telefono=turno.contacto_telefono if alcance.puede_escribir else None,
            sena=None if estado_pago is None else SenaAgenda(estado=estado_pago, monto=monto_pago),
            vence_en=turno.en_espera_vence_en.astimezone(zona) if turno.en_espera_vence_en else None,
            acciones=acciones_permitidas(turno.estado, turno.inicio, ahora, permiso, zona, tolerancia),
        ))
    # C-10: estado del evento de Google por turno y franjas ocupadas del alcance (sin título, O19).
    calendario = await calendario_de_turnos(session, [t.id for t in turnos])
    for item in turnos:
        estado_evento, conflicto = calendario.get(item.id, ("sin_evento", False))
        item.calendario = CalendarioTurno(estado=estado_evento, conflicto_abierto=conflicto)  # type: ignore[arg-type]
    ocupados = [OcupadoGoogle(profesional_id=f.profesional_id, inicio=f.inicio.astimezone(zona),
                              fin=f.fin.astimezone(zona))
                for f in await franjas_ocupadas(session, desde, hasta, profesional_id=profesional_filtro)]
    return AgendaResponse(vista=query.vista, desde=primero, hasta=ultimo, turnos=turnos, ocupados_google=ocupados)


async def consultar_opciones(session: AsyncSession, alcance: Alcance) -> OpcionesResponse:
    """Profesionales visibles, sillones activos y tratamientos: una sola llamada para los filtros y el alta."""
    profesionales = select(Profesional).order_by(Profesional.nombre, Profesional.id)
    if alcance.profesional_id is not None:
        profesionales = profesionales.where(Profesional.id == alcance.profesional_id)
    sillones = select(Sillon).where(Sillon.estado == "activo").order_by(Sillon.nombre, Sillon.id)
    tratamientos = select(Tratamiento).order_by(Tratamiento.nombre, Tratamiento.id)
    return OpcionesResponse(
        profesionales=[Ref(id=p.id, nombre=p.nombre) for p in (await session.execute(profesionales)).scalars()],
        sillones=[Ref(id=s.id, nombre=s.nombre) for s in (await session.execute(sillones)).scalars()],
        tratamientos=[TratamientoRef(id=t.id, nombre=t.nombre, duracion_minutos=t.duracion_minutos)
                      for t in (await session.execute(tratamientos)).scalars()],
        puede_escribir=alcance.puede_escribir,
    )


# ---------------------------------------------------------------------------
# Alta manual (D3)
# ---------------------------------------------------------------------------

class InicioPasadoError(Exception):
    """El inicio pedido ya pasó (422 ``inicio_pasado``, O9)."""

    def __init__(self) -> None:
        super().__init__("El horario elegido ya pasó")


async def _conflicto(session: AsyncSession, motivo: str, profesional_id: int, inicio: datetime,
                     minutos: int) -> ReservaConflictoError:
    """Arma el 409 con alternativas libres; libera el lock y cualquier estado de la transacción."""
    alternativas = await _alternativas(session, profesional_id, inicio, minutos)
    await session.rollback()
    return ReservaConflictoError(motivo=motivo, alternativas=alternativas)


async def crear_turno_manual(session: AsyncSession, data: TurnoManualCreate, usuario_id: int,
                             ahora: datetime) -> TurnoManualCreado:
    """Alta manual de recepción/admin: ``reservado`` sin seña (O7), con la misma garantía anti-solape que la reserva
    pública (advisory lock + pre-chequeo + EXCLUDE de la base como garantía final, R5).

    Raises:
        ReferenceNotFoundError: profesional, tratamiento o sillón inexistente (422).
        InicioPasadoError: ``inicio <= ahora`` (422).
        FueraDeDisponibilidadError: no entra completo en una franja vigente (422, RN-TU-07).
        ReservaConflictoError: solape de profesional o sillón, con alternativas (409).
    """
    if await session.get(Profesional, data.profesional_id) is None:
        raise ReferenceNotFoundError(campo="profesional_id")
    tratamiento = await session.get(Tratamiento, data.tratamiento_id)
    if tratamiento is None:
        raise ReferenceNotFoundError(campo="tratamiento_id")
    elegido = None
    if data.sillon_id is not None:
        elegido = await session.get(Sillon, data.sillon_id)
        if elegido is None:
            raise ReferenceNotFoundError(campo="sillon_id")

    inicio = data.inicio
    minutos = tratamiento.duracion_minutos
    fin = inicio + timedelta(minutes=minutos)  # RN-TU-04/05: duración vigente
    if inicio <= ahora:
        raise InicioPasadoError()
    sillon_defecto = await _franja_que_contiene(session, data.profesional_id, inicio, fin)
    if sillon_defecto is False:
        raise FueraDeDisponibilidadError()

    # Mismo orden de locks que la reserva pública: serializa altas, reservas y acreditaciones.
    await session.execute(select(func.pg_advisory_xact_lock(LOCK_RESERVAS)))
    bloqueos = await _cargar_bloqueos(session, inicio, fin, incluir_google=False)  # C-10 O10: Google solo avisa
    if _profesional_ocupado(bloqueos, data.profesional_id, inicio, fin):
        raise await _conflicto(session, "profesional", data.profesional_id, inicio, minutos)
    if elegido is not None:
        libre = elegido.estado == "activo" and _sillon_libre([elegido], bloqueos, inicio, fin) is not None
        sillon = elegido if libre else None
    else:
        sillon = _sillon_libre(await _sillones_activos(session), bloqueos, inicio, fin,
                               sillon_defecto if isinstance(sillon_defecto, int) else None)
    if sillon is None:
        raise await _conflicto(session, "sillon", data.profesional_id, inicio, minutos)

    turno = Turno(
        profesional_id=data.profesional_id, sillon_id=sillon.id, tratamiento_id=data.tratamiento_id,
        paciente_id=None, inicio=inicio, fin=fin, estado="reservado", origen="manual",
        codigo_gestion=str(uuid.uuid4()), contacto_nombre=data.nombre, contacto_telefono=data.telefono,
    )
    session.add(turno)
    try:
        await session.flush()
        await session.refresh(turno)  # Identity: el id no se rellena tras el flush sin refresh
        session.add(RegistroAuditoria(  # RN-GL-01: misma transacción; sin nombre, teléfono ni código (R19)
            usuario_id=usuario_id, accion="CREATE", entidad="turno", entidad_id=str(turno.id),
            datos_despues={
                "profesional_id": turno.profesional_id, "sillon_id": turno.sillon_id,
                "tratamiento_id": turno.tratamiento_id, "inicio": turno.inicio.isoformat(),
                "fin": turno.fin.isoformat(), "estado": turno.estado, "origen": "alta_manual_panel",
            },
            ip=None,
        ))
        await session.commit()
    except (IntegrityError, DBAPIError) as exc:
        await session.rollback()
        sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", "")
        if sqlstate in (SQLSTATE_EXCLUSION, SQLSTATE_DEADLOCK):  # red de seguridad (R5): nunca 500
            motivo = motivo_desde_mensaje(str(exc.orig)) if sqlstate == SQLSTATE_EXCLUSION else "profesional"
            raise await _conflicto(session, motivo, data.profesional_id, inicio, minutos) from exc
        raise

    zona = zona_clinica()
    aviso_google = bool(await franjas_ocupadas(session, turno.inicio, turno.fin, profesional_id=turno.profesional_id))
    return TurnoManualCreado(
        id=int(turno.id), inicio=turno.inicio.astimezone(zona), fin=turno.fin.astimezone(zona), estado="reservado",
        origen="manual", profesional_id=turno.profesional_id, sillon_id=turno.sillon_id,
        tratamiento_id=turno.tratamiento_id, codigo_gestion=turno.codigo_gestion or "",
        aviso_google_calendar=aviso_google,
    )


# ---------------------------------------------------------------------------
# Cambios de estado: ausente, atendido y cancelar (D4, D5)
# ---------------------------------------------------------------------------

async def marcar_turno(session: AsyncSession, turno_id: int, destino: str, usuario_id: int,
                       ahora: datetime, profesional_requerido: int | None = None) -> ResultadoCambioEstado:
    """Marca ``ausente`` o ``atendido`` aplicando RN-TU-12 bajo lock con el inicio real del turno (O14).

    - ``ausente``: desde ``inicio + tolerancia``; una seña acreditada queda ``no_reembolsado`` (R9).
    - ``atendido``: desde las 00:00 del día local del turno; la seña no cambia y el turno sigue ocupando (O19).
    No publica eventos (O15).

    ``profesional_requerido`` (C-11, O15): la odontóloga solo marca turnos de su profesional; se valida bajo el lock del
    turno y antes que la transición y el horario (``TurnoAjenoError``).
    """
    zona = zona_clinica()
    if destino == "ausente":
        tolerancia = tolerancia_ausente()

        def habilitado(inicio: datetime) -> datetime:
            return ausente_habilitado_desde(inicio, tolerancia)

        origen = "marcado_ausente_panel"
    else:
        def habilitado(inicio: datetime) -> datetime:
            return atendido_habilitado_desde(inicio, zona)

        origen = "marcado_atendido_panel"
    return await cambiar_estado_turno(session, turno_id, destino, usuario_id, ahora=ahora, origen=origen,
                                      habilitado_desde=habilitado, profesional_requerido=profesional_requerido)


async def cancelar_turno_panel(session: AsyncSession, turno_id: int, usuario_id: int, ahora: datetime,
                               notificador: NotificadorTurnos) -> ResultadoCambioEstado:
    """Cancela desde el panel con las mismas reglas que el paciente (RN-TU-01, RN-SN-04, O12).

    Publica ``turno_cancelado`` después del commit solo si el turno ocupaba agenda; una falla del publicador no
    revierte nada.

    Raises:
        TurnoInexistenteError, TransicionInvalidaError, OperacionReintentableError: ver ``cambiar_estado_turno``.
        FueraDePlazoError: faltan menos de 24 h para un reservado/confirmado.
    """
    try:
        r = await cambiar_estado_turno(session, turno_id, "cancelado", usuario_id, ahora=ahora,
                                       origen="cancelacion_panel")
    except CancelacionFueraDePlazoError as exc:
        inicio = (await session.execute(select(Turno.inicio).where(Turno.id == turno_id))).scalar_one()
        raise FueraDePlazoError(limite_cambios(inicio, zona_clinica())) from exc
    if r.estado_anterior in ESTADOS_GESTIONABLES:  # un en_espera nunca tuvo calendario ni recordatorio (RN-SN-01)
        await publicar_sin_romper(notificador, EventoTurno(
            tipo="turno_cancelado", turno_id=r.turno_id, profesional_id=r.profesional_id,
            inicio_anterior=r.inicio, fin_anterior=r.fin, inicio_nuevo=None, fin_nuevo=None, ocurrido_en=ahora))
    return r
