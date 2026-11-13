"""Operación de recepción sobre los recordatorios (C-09, D7): listar, marcar enviado y marcar fallido.

El listado filtra por el estado ACTUAL del turno (``turno_inicio = turno.inicio`` y turno reservado o confirmado), así un
recordatorio viejo nunca se muestra aunque la anulación inmediata no haya corrido (D6). El link ``wa.me`` se arma al
responder y no se persiste ni se loguea (R19). Cada escritura deja auditoría sin teléfono, nombre ni link (RN-GL-01).
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Paciente
from app.plataforma.auditoria import registrar
from app.notificaciones.mensaje import DatosMensaje, armar_mensaje, link_wa_me
from app.notificaciones.models import Recordatorio
from app.notificaciones.schemas import EstadoVisible, RecordatorioOut
from app.notificaciones.service import telefono_valido
from app.shared.settings import get_settings
from app.turnos.models import Profesional, Tratamiento, Turno

ESTADOS_TURNO_VIGENTE = ("reservado", "confirmado")
ESTADOS_CON_LINK = ("pendiente", "enviado", "fallido")
ESTADOS_POR_DEFECTO: tuple[EstadoVisible, ...] = ("pendiente", "fallido")


class RecordatorioInexistenteError(Exception):
    """No existe el recordatorio (404 ``recordatorio_inexistente``)."""

    def __init__(self) -> None:
        super().__init__("No encontramos ese recordatorio")


class RecordatorioNoVigenteError(Exception):
    """Está confirmado, anulado o su turno cambió de horario o estado (409 ``recordatorio_no_vigente``)."""

    def __init__(self) -> None:
        super().__init__("Ese recordatorio ya no corresponde: el turno se confirmó, se canceló o cambió de horario")


def _consulta_base():  # type: ignore[no-untyped-def]
    return (select(Recordatorio, Turno, Profesional.nombre, Tratamiento.nombre, Paciente.telefono, Paciente.nombre,
                   Paciente.apellido)
            .join(Turno, Turno.id == Recordatorio.turno_id)
            .join(Profesional, Profesional.id == Turno.profesional_id)
            .join(Tratamiento, Tratamiento.id == Turno.tratamiento_id)
            .outerjoin(Paciente, Paciente.id == Turno.paciente_id))


def _item(fila: tuple, zona: ZoneInfo) -> RecordatorioOut:  # type: ignore[type-arg]
    recordatorio, turno, profesional, tratamiento, tel_paciente, nombre_pac, apellido_pac = fila
    ajustes = get_settings()
    nombre = turno.contacto_nombre or (f"{nombre_pac} {apellido_pac}" if nombre_pac else None)
    telefono = telefono_valido(turno.contacto_telefono, tel_paciente)
    link = None
    if telefono is not None and recordatorio.estado in ESTADOS_CON_LINK:
        texto = armar_mensaje(
            DatosMensaje(nombre=nombre, inicio=turno.inicio, profesional=profesional, tratamiento=tratamiento,
                         codigo_gestion=turno.codigo_gestion),
            zona, ajustes.public_base_url, ajustes.clinica_nombre)
        link = link_wa_me(telefono, texto)
    return RecordatorioOut(
        id=recordatorio.id, turno_id=turno.id, estado=recordatorio.estado, motivo=recordatorio.motivo,
        turno_inicio=turno.inicio.astimezone(zona), profesional=profesional, tratamiento=tratamiento,
        contacto_nombre=nombre, enviado_en=recordatorio.enviado_en, intentos_fallidos=recordatorio.intentos_fallidos,
        link=link)


async def listar_recordatorios(session: AsyncSession, ahora: datetime,
                               estados: tuple[EstadoVisible, ...] = ESTADOS_POR_DEFECTO) -> list[RecordatorioOut]:
    """Recordatorios vigentes de los turnos que empiezan dentro de la anticipación, por inicio del turno."""
    ajustes = get_settings()
    zona = ZoneInfo(ajustes.app_tz)
    limite: datetime = ahora + timedelta(hours=ajustes.reminder_lead_time)
    filas = (await session.execute(
        _consulta_base()
        .where(Recordatorio.estado.in_(estados), Recordatorio.turno_inicio == Turno.inicio,
               Turno.estado.in_(ESTADOS_TURNO_VIGENTE), Turno.inicio > ahora, Turno.inicio <= limite)
        .order_by(Turno.inicio, Recordatorio.id))).all()
    return [_item(tuple(f), zona) for f in filas]


async def _cargar_vigente(session: AsyncSession, recordatorio_id: int) -> tuple:  # type: ignore[type-arg]
    fila = (await session.execute(
        _consulta_base().where(Recordatorio.id == recordatorio_id)
        .with_for_update(of=Recordatorio).execution_options(populate_existing=True))).first()
    if fila is None:
        await session.rollback()
        raise RecordatorioInexistenteError()
    recordatorio, turno = fila[0], fila[1]
    if (recordatorio.estado in ("confirmado", "anulado") or recordatorio.turno_inicio != turno.inicio
            or turno.estado not in ESTADOS_TURNO_VIGENTE):
        await session.rollback()
        raise RecordatorioNoVigenteError()
    return tuple(fila)


def _auditar(session: AsyncSession, usuario_id: int, recordatorio: Recordatorio, antes: dict[str, object],
             despues: dict[str, object]) -> None:
    registrar(session, accion="UPDATE", entidad="recordatorio", entidad_id=recordatorio.id, usuario_id=usuario_id,
              antes=antes, despues={**despues, "turno_id": recordatorio.turno_id})


async def marcar_enviado(session: AsyncSession, recordatorio_id: int, usuario_id: int,
                         ahora: datetime) -> RecordatorioOut:
    """Recepción abrió WhatsApp (O2): ``pendiente``/``fallido`` -> ``enviado``; un ``enviado`` se vuelve a marcar (reenvío)."""
    fila = await _cargar_vigente(session, recordatorio_id)
    recordatorio: Recordatorio = fila[0]
    antes = {"estado": recordatorio.estado, "motivo": recordatorio.motivo}
    recordatorio.estado, recordatorio.motivo = "enviado", None
    recordatorio.enviado_en, recordatorio.enviado_por_usuario_id = ahora, usuario_id
    recordatorio.proximo_intento_en = None
    _auditar(session, usuario_id, recordatorio, antes, {"estado": "enviado", "origen": "envio_manual"})
    await session.commit()
    return _item(fila, ZoneInfo(get_settings().app_tz))


async def marcar_fallido(session: AsyncSession, recordatorio_id: int, usuario_id: int, motivo: str) -> RecordatorioOut:
    """Recepción no pudo avisar: ``pendiente``/``enviado`` -> ``fallido`` con motivo."""
    fila = await _cargar_vigente(session, recordatorio_id)
    recordatorio: Recordatorio = fila[0]
    antes = {"estado": recordatorio.estado, "motivo": recordatorio.motivo}
    recordatorio.estado, recordatorio.motivo = "fallido", motivo
    recordatorio.proximo_intento_en = None
    _auditar(session, usuario_id, recordatorio, antes, {"estado": "fallido", "motivo": motivo, "origen": "fallo_manual"})
    await session.commit()
    return _item(fila, ZoneInfo(get_settings().app_tz))
