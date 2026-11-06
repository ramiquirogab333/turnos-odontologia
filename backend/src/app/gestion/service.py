"""Servicio de gestión del turno por el paciente: consultar y cancelar con el código de gestión (C-07).

- La regla de 24 h vive en ``app.pagos.estados`` (``dentro_de_ventana``): una sola fuente (RN-TU-01/02).
- La cancelación reutiliza ``cambiar_estado_turno`` de C-06 (orden de locks advisory -> turno -> pago).
- Los eventos se publican DESPUÉS del commit y una falla del publicador nunca revierte la operación.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.gestion.errores import (
    FueraDePlazoError,
    GestionNoEncontradaError,
    HorarioInvalidoError,
    SenaPendienteError,
    TurnoNoModificableError,
)
from app.gestion.eventos import EventoTurno, NotificadorTurnos
from app.gestion.schemas import MotivoNoModificable
from app.pagos.config import obtener_configuracion
from app.models.core import RegistroAuditoria
from app.pagos.errores import OperacionReintentableError, TurnoInexistenteError
from app.pagos.estados import (
    CancelacionFueraDePlazoError,
    TransicionInvalidaError,
    dentro_de_ventana,
    limite_cambios,
)
from app.pagos.models import PagoSena
from app.pagos.service import ResultadoCambioEstado, cambiar_estado_turno
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
from app.shared.logger import get_logger
from app.shared.settings import get_settings
from app.turnos.models import Profesional, Tratamiento, Turno
from app.turnos.service import motivo_desde_mensaje

logger = get_logger(__name__)

SQLSTATE_SERIALIZACION = "40001"
MAX_REINTENTOS = 2
LARGO_MIN_CODIGO = 8  # igual que el CHECK de turno.codigo_gestion (migración 005)
LARGO_MAX_CODIGO = 64
ESTADOS_BLOQUEANTES = ("reservado", "confirmado")
ESTADOS_FINALES = ("cancelado", "ausente", "atendido")


def zona_clinica() -> ZoneInfo:
    return ZoneInfo(get_settings().app_tz)


async def turno_id_por_codigo(session: AsyncSession, codigo: str | None) -> int:
    """Id del turno cuyo código coincide. Ausente, de largo inválido, desconocido o interno: el mismo 404."""
    if not codigo or not (LARGO_MIN_CODIGO <= len(codigo) <= LARGO_MAX_CODIGO):
        raise GestionNoEncontradaError()
    turno_id = (await session.execute(select(Turno.id).where(Turno.codigo_gestion == codigo))).scalar_one_or_none()
    if turno_id is None:
        raise GestionNoEncontradaError()
    return int(turno_id)


def _motivos(estado: str, inicio: datetime, ahora: datetime) -> tuple[MotivoNoModificable | None,
                                                                      MotivoNoModificable | None]:
    """(motivo para no cancelar, motivo para no reprogramar); ``None`` si la acción está permitida."""
    if estado in ESTADOS_FINALES:
        return "turno_no_modificable", "turno_no_modificable"
    if estado == "en_espera":  # cancelar no tiene ventana (O10); reprogramar exige seña acreditada (O3)
        return None, "sena_pendiente"
    fuera = None if dentro_de_ventana(inicio, ahora) else "fuera_de_plazo"
    return fuera, fuera


async def consultar_gestion(session: AsyncSession, codigo: str | None, *, ahora: datetime) -> dict[str, object]:
    """Datos del turno para gestionarlo, sin teléfono ni nombre de contacto."""
    turno_id = await turno_id_por_codigo(session, codigo)
    turno = (await session.execute(select(Turno).where(Turno.id == turno_id))).scalar_one()
    tratamiento = await session.get(Tratamiento, turno.tratamiento_id)
    profesional = await session.get(Profesional, turno.profesional_id)
    pago = (await session.execute(
        select(PagoSena).where(PagoSena.turno_id == turno.id).order_by(PagoSena.id.desc()).limit(1)
    )).scalar_one_or_none()
    config = await obtener_configuracion(session)
    assert tratamiento is not None and profesional is not None  # FK obligatorias
    zona = zona_clinica()
    no_cancelable, no_reprogramable = _motivos(turno.estado, turno.inicio, ahora)
    return {
        "estado": turno.estado,
        "inicio": turno.inicio.astimezone(zona),
        "fin": turno.fin.astimezone(zona),
        "tratamiento": {"id": tratamiento.id, "nombre": tratamiento.nombre,
                        "duracion_minutos": tratamiento.duracion_minutos},
        "profesional": {"id": profesional.id, "nombre": profesional.nombre},
        "sena": None if pago is None else {"monto": pago.monto, "estado": pago.estado},
        "limite_cambios": limite_cambios(turno.inicio, zona),
        "puede_cancelar": no_cancelable is None,
        "puede_reprogramar": no_reprogramable is None,
        "motivo_no_cancelable": no_cancelable,
        "motivo_no_reprogramable": no_reprogramable,
        "texto_politica_reembolso": config.texto_politica_reembolso,
    }


async def publicar_sin_romper(notificador: NotificadorTurnos, evento: EventoTurno) -> None:
    """Publica después del commit; una falla se loguea (sin PII) y no revierte nada (D5)."""
    try:
        await notificador.publicar(evento)
    except Exception:  # noqa: BLE001 - el publicador es un colaborador externo
        logger.exception("no se pudo publicar el evento %s del turno %s", evento.tipo, evento.turno_id)


async def cancelar_turno_publico(session: AsyncSession, codigo: str | None, *, ahora: datetime,
                                 notificador: NotificadorTurnos) -> ResultadoCambioEstado:
    """Cancela el turno del paciente (RN-TU-01, RN-SN-04, RN-SN-10).

    Raises:
        GestionNoEncontradaError: código inválido (404).
        TurnoNoModificableError: estado final (409).
        FueraDePlazoError: faltan menos de 24 h para un reservado/confirmado (409).
        OperacionReintentableError: agotados los reintentos transitorios (503).
    """
    turno_id = await turno_id_por_codigo(session, codigo)
    try:
        r = await cambiar_estado_turno(session, turno_id, "cancelado", None, ahora=ahora,
                                       origen="cancelacion_paciente")
    except TurnoInexistenteError as exc:
        raise GestionNoEncontradaError() from exc
    except TransicionInvalidaError as exc:
        raise TurnoNoModificableError(exc.actual) from exc
    except CancelacionFueraDePlazoError as exc:
        inicio = (await session.execute(select(Turno.inicio).where(Turno.id == turno_id))).scalar_one()
        raise FueraDePlazoError(limite_cambios(inicio, zona_clinica())) from exc
    if r.estado_anterior in ESTADOS_BLOQUEANTES:  # un en_espera nunca tuvo calendario ni recordatorio (RN-SN-01)
        await publicar_sin_romper(notificador, EventoTurno(
            tipo="turno_cancelado", turno_id=r.turno_id, profesional_id=r.profesional_id,
            inicio_anterior=r.inicio, fin_anterior=r.fin, inicio_nuevo=None, fin_nuevo=None, ocurrido_en=ahora))
    return r


async def _reprogramar_una_vez(session: AsyncSession, turno_id: int, nuevo_inicio: datetime, *,
                               ahora: datetime) -> tuple[dict[str, object], EventoTurno]:
    """Una pasada de la reprogramación (D3). Advisory lock -> turno -> pago, como en C-06."""
    await session.execute(select(func.pg_advisory_xact_lock(LOCK_RESERVAS)))
    turno = (await session.execute(
        select(Turno).where(Turno.id == turno_id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if turno is None:
        await session.rollback()
        raise GestionNoEncontradaError()
    if turno.estado == "en_espera":
        await session.rollback()
        raise SenaPendienteError()
    if turno.estado not in ESTADOS_BLOQUEANTES:
        estado_actual = turno.estado  # antes del rollback, que expira los atributos
        await session.rollback()
        raise TurnoNoModificableError(estado_actual)
    zona = zona_clinica()
    if not dentro_de_ventana(turno.inicio, ahora):
        limite = limite_cambios(turno.inicio, zona)
        await session.rollback()
        raise FueraDePlazoError(limite)
    if nuevo_inicio == turno.inicio:
        await session.rollback()
        raise HorarioInvalidoError("mismo_horario")
    if nuevo_inicio <= ahora:
        await session.rollback()
        raise HorarioInvalidoError("horario_pasado")

    tratamiento = await session.get(Tratamiento, turno.tratamiento_id)
    assert tratamiento is not None  # FK obligatoria
    minutos = tratamiento.duracion_minutos  # duración vigente (RN-TU-04/05)
    nuevo_fin = nuevo_inicio + timedelta(minutes=minutos)
    sillon_defecto = await _franja_que_contiene(session, turno.profesional_id, nuevo_inicio, nuevo_fin)
    if sillon_defecto is False:  # RN-TU-07
        await session.rollback()
        raise FueraDeDisponibilidadError()

    pago = (await session.execute(  # solo se lee y se bloquea: la seña acompaña al turno sin cambios
        select(PagoSena).where(PagoSena.turno_id == turno.id, PagoSena.estado == "acreditado")
        .with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()

    bloqueos = await _cargar_bloqueos(session, nuevo_inicio, nuevo_fin, excluir_turno_id=turno.id)
    motivo: str | None = None
    sillon = None
    if _profesional_ocupado(bloqueos, turno.profesional_id, nuevo_inicio, nuevo_fin):
        motivo = "profesional"
    else:
        sillon = _sillon_libre(await _sillones_activos(session), bloqueos, nuevo_inicio, nuevo_fin,
                               sillon_defecto if isinstance(sillon_defecto, int) else turno.sillon_id)
        if sillon is None:
            motivo = "sillon"
    if motivo is not None:
        raise await _conflicto_reprogramacion(session, motivo, turno.profesional_id, nuevo_inicio, minutos)
    assert sillon is not None

    antes = {"inicio": turno.inicio.isoformat(), "fin": turno.fin.isoformat(),
             "sillon_id": turno.sillon_id, "estado": turno.estado}
    inicio_anterior, fin_anterior = turno.inicio, turno.fin
    profesional_id = turno.profesional_id
    estado_sena = pago.estado if pago else None
    turno.inicio, turno.fin, turno.sillon_id = nuevo_inicio, nuevo_fin, sillon.id
    turno.estado = "reservado"  # un confirmado vuelve a reservado (O5)
    session.add(RegistroAuditoria(  # RN-GL-01: misma transacción, sin PII de contacto
        usuario_id=None, accion="UPDATE", entidad="turno", entidad_id=str(turno.id), datos_antes=antes,
        datos_despues={"inicio": nuevo_inicio.isoformat(), "fin": nuevo_fin.isoformat(),
                       "sillon_id": sillon.id, "estado": "reservado", "origen": "reprogramacion_paciente"},
        ip=None))
    try:
        await session.flush()  # los EXCLUDE de la base son la garantía final (R5)
        await session.commit()
    except (IntegrityError, DBAPIError) as exc:
        await session.rollback()
        sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", "")
        if sqlstate in (SQLSTATE_EXCLUSION, SQLSTATE_DEADLOCK):  # red de seguridad: nunca 500
            motivo_db = motivo_desde_mensaje(str(exc.orig)) if sqlstate == SQLSTATE_EXCLUSION else "profesional"
            raise await _conflicto_reprogramacion(session, motivo_db, profesional_id, nuevo_inicio, minutos) from exc
        raise
    respuesta: dict[str, object] = {
        "estado": "reservado", "inicio": nuevo_inicio.astimezone(zona), "fin": nuevo_fin.astimezone(zona),
        "estado_sena": estado_sena}
    evento = EventoTurno(
        tipo="turno_reprogramado", turno_id=turno_id, profesional_id=profesional_id,
        inicio_anterior=inicio_anterior, fin_anterior=fin_anterior, inicio_nuevo=nuevo_inicio,
        fin_nuevo=nuevo_fin, ocurrido_en=ahora)
    return respuesta, evento


async def _conflicto_reprogramacion(session: AsyncSession, motivo: str, profesional_id: int, nuevo_inicio: datetime,
                                    minutos: int) -> ReservaConflictoError:
    """409 con alternativas; libera el lock y la transacción."""
    alternativas = await _alternativas(session, profesional_id, nuevo_inicio, minutos)
    await session.rollback()
    return ReservaConflictoError(motivo=motivo, alternativas=alternativas)


async def reprogramar_turno_publico(session: AsyncSession, codigo: str | None, nuevo_inicio: datetime, *,
                                    ahora: datetime, notificador: NotificadorTurnos) -> dict[str, object]:
    """Mueve el turno en el lugar (mismo id, código y seña) a un horario libre de la misma profesional.

    Raises:
        GestionNoEncontradaError (404), SenaPendienteError / TurnoNoModificableError / FueraDePlazoError /
        ReservaConflictoError (409), HorarioInvalidoError / FueraDeDisponibilidadError (422),
        OperacionReintentableError (503).
    """
    turno_id = await turno_id_por_codigo(session, codigo)
    for intento in range(MAX_REINTENTOS + 1):
        try:
            respuesta, evento = await _reprogramar_una_vez(session, turno_id, nuevo_inicio, ahora=ahora)
        except (IntegrityError, DBAPIError) as exc:
            await session.rollback()
            sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", "")
            if sqlstate != SQLSTATE_SERIALIZACION:
                raise
            logger.warning("reprogramación: %s en el intento %s del turno %s", sqlstate, intento + 1, turno_id)
            continue
        await publicar_sin_romper(notificador, evento)
        return respuesta
    raise OperacionReintentableError()
