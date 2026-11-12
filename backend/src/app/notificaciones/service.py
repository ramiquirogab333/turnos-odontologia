"""Ciclo de recordatorios (C-09, D3): reconciliar, generar y procesar con el proveedor.

``generar_recordatorios`` es una función ``(session, ahora)`` pura respecto del reloj: la ejecuta el worker y la
prueban los tests con un ``ahora`` fijo. Es idempotente y segura con varios workers a la vez: la generación es
``INSERT ... ON CONFLICT DO NOTHING`` sobre el índice único parcial (un vigente por turno y horario) y el reintento
toma las filas con ``FOR UPDATE SKIP LOCKED``. El log solo lleva cantidades (R19, Ley 25.326); nunca teléfono, nombre,
link ni código de gestión.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import DateTime, and_, case, exists, literal, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Paciente
from app.notificaciones.mensaje import DatosMensaje, armar_mensaje
from app.notificaciones.models import Recordatorio
from app.notificaciones.proveedor import DatosEnvio, ErrorTransitorioProveedor, ProveedorWhatsApp
from app.shared.logger import get_logger
from app.shared.settings import get_settings
from app.turnos.models import Profesional, Tratamiento, Turno

logger = get_logger(__name__)

E164 = r"^\+[1-9][0-9]{1,14}$"
_E164_RE = re.compile(E164)
# Esperas ante un error transitorio del proveedor (O10): reintentos a 1, 5 y 15 minutos.
ESPERAS_REINTENTO = (timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=15))
ESTADOS_ANULABLES = ("pendiente", "enviado", "fallido", "confirmado")
LARGO_MAX_ERROR = 500

_DATO_PERSONAL = re.compile(r"(https?://\S+|\S+@\S+|\+?\d[\d\s().-]{5,}\d)")


@dataclass(frozen=True)
class ResumenCiclo:
    """Cantidades del ciclo (lo único que se loguea)."""

    reconciliados: int = 0
    generados: int = 0
    sin_telefono: int = 0
    procesados: int = 0
    fallidos: int = 0


def telefono_valido(*candidatos: str | None) -> str | None:
    """Primer teléfono en formato E.164 entre el del turno y el de la ficha; se usa tal cual (O16)."""
    for candidato in candidatos:
        if candidato and _E164_RE.fullmatch(candidato):
            return candidato
    return None


def sanitizar_error(error: BaseException) -> str:
    """Texto guardable de un error del proveedor: sin teléfonos, correos ni enlaces, acotado a 500 caracteres."""
    detalle = _DATO_PERSONAL.sub("[dato]", str(error))
    return f"{type(error).__name__}: {detalle}"[:LARGO_MAX_ERROR]


async def _reconciliar(session: AsyncSession, ahora: datetime) -> int:
    """Paso 1: anula los recordatorios que dejaron de corresponder al turno (cancelado, movido o iniciado)."""
    limpio = {"proximo_intento_en": None, "confirmado_en": None}
    total = 0
    # El turno ya está ``confirmado`` (RN-WA-02) pero el recordatorio no se enteró: se cierra con la hora del ciclo.
    cerrados = await session.execute(
        update(Recordatorio)
        .where(Recordatorio.estado.in_(("pendiente", "enviado", "fallido")),
               exists().where(Turno.id == Recordatorio.turno_id, Turno.estado == "confirmado",
                              Turno.inicio == Recordatorio.turno_inicio))
        .values(estado="confirmado", confirmado_en=ahora, motivo=None, proximo_intento_en=None)
        .execution_options(synchronize_session=False))
    total += cerrados.rowcount or 0
    for motivo, condiciones in (
        ("turno_cancelado", [Recordatorio.estado.in_(ESTADOS_ANULABLES),
                             exists().where(Turno.id == Recordatorio.turno_id, Turno.estado == "cancelado")]),
        ("turno_reprogramado", [Recordatorio.estado.in_(ESTADOS_ANULABLES),
                                exists().where(Turno.id == Recordatorio.turno_id,
                                               Turno.inicio != Recordatorio.turno_inicio)]),
        ("turno_iniciado", [Recordatorio.estado.in_(("pendiente", "fallido")),
                            exists().where(Turno.id == Recordatorio.turno_id, Turno.inicio <= ahora)]),
    ):
        resultado = await session.execute(
            update(Recordatorio).where(*condiciones)
            .values(estado="anulado", motivo=motivo, **limpio)
            .execution_options(synchronize_session=False))
        total += resultado.rowcount or 0
    return total


async def _generar(session: AsyncSession, ahora: datetime, anticipacion: timedelta) -> list[tuple[int, str]]:
    """Paso 2: un recordatorio por turno ``reservado`` dentro de la anticipación que aún no tenga uno vigente."""
    tiene_telefono = or_(Turno.contacto_telefono.op("~")(E164), Paciente.telefono.op("~")(E164))
    candidatos = (
        select(
            Turno.id, literal("whatsapp"), case((tiene_telefono, "pendiente"), else_="fallido"), Turno.inicio,
            literal(ahora, type_=DateTime(timezone=True)), case((tiene_telefono, None), else_="sin_telefono"),
            literal(0))
        .select_from(Turno).outerjoin(Paciente, Paciente.id == Turno.paciente_id)
        .where(Turno.estado == "reservado", Turno.inicio > ahora, Turno.inicio <= ahora + anticipacion,
               ~exists().where(Recordatorio.turno_id == Turno.id, Recordatorio.turno_inicio == Turno.inicio,
                               Recordatorio.estado != "anulado")))
    insercion = (
        pg_insert(Recordatorio)
        .from_select(["turno_id", "canal", "estado", "turno_inicio", "generado_en", "motivo", "intentos_fallidos"],
                     candidatos)
        .on_conflict_do_nothing(index_elements=[Recordatorio.turno_id, Recordatorio.turno_inicio],
                                index_where=text("estado <> 'anulado'"))
        .returning(Recordatorio.id, Recordatorio.estado))
    return [(int(i), str(e)) for i, e in (await session.execute(insercion)).all()]


async def _procesar(session: AsyncSession, ahora: datetime, proveedor: ProveedorWhatsApp,
                    nuevos: set[int]) -> tuple[int, int]:
    """Paso 3: pasa por el proveedor los pendientes nuevos y los reintentos vencidos. Devuelve (procesados, fallidos)."""
    ajustes = get_settings()
    zona = ZoneInfo(ajustes.app_tz)
    filas = (await session.execute(
        select(Recordatorio, Turno, Profesional.nombre, Tratamiento.nombre, Paciente.telefono, Paciente.nombre)
        .join(Turno, Turno.id == Recordatorio.turno_id)
        .join(Profesional, Profesional.id == Turno.profesional_id)
        .join(Tratamiento, Tratamiento.id == Turno.tratamiento_id)
        .outerjoin(Paciente, Paciente.id == Turno.paciente_id)
        .where(Recordatorio.estado == "pendiente",
               or_(Recordatorio.id.in_(nuevos),
                   and_(Recordatorio.proximo_intento_en.is_not(None), Recordatorio.proximo_intento_en <= ahora)))
        .order_by(Recordatorio.id)
        .with_for_update(of=Recordatorio, skip_locked=True)
        .execution_options(populate_existing=True))).all()
    procesados = fallidos = 0
    for recordatorio, turno, profesional, tratamiento, tel_paciente, nombre_paciente in filas:
        telefono = telefono_valido(turno.contacto_telefono, tel_paciente)
        if telefono is None:  # el teléfono desapareció después de generarlo
            recordatorio.estado, recordatorio.motivo, recordatorio.proximo_intento_en = (
                "fallido", "sin_telefono", None)
            fallidos += 1
            continue
        texto = armar_mensaje(
            DatosMensaje(nombre=turno.contacto_nombre or nombre_paciente, inicio=turno.inicio, profesional=profesional,
                         tratamiento=tratamiento, codigo_gestion=turno.codigo_gestion),
            zona, ajustes.public_base_url, ajustes.clinica_nombre)
        procesados += 1
        try:
            resultado = await proveedor.procesar(DatosEnvio(int(recordatorio.id), telefono, texto))
        except Exception as error:  # noqa: BLE001 - cualquier falla del proveedor es reintentable y no mata el ciclo
            recordatorio.intentos_fallidos += 1
            recordatorio.ultimo_error = sanitizar_error(error)
            if recordatorio.intentos_fallidos > len(ESPERAS_REINTENTO):
                recordatorio.estado, recordatorio.motivo, recordatorio.proximo_intento_en = (
                    "fallido", "error_proveedor", None)
                fallidos += 1
            else:
                recordatorio.proximo_intento_en = ahora + ESPERAS_REINTENTO[recordatorio.intentos_fallidos - 1]
            continue
        recordatorio.proximo_intento_en = None
        if resultado == "enviado":
            recordatorio.estado, recordatorio.enviado_en = "enviado", ahora
    return procesados, fallidos


async def generar_recordatorios(session: AsyncSession, ahora: datetime, anticipacion: timedelta,
                                proveedor: ProveedorWhatsApp) -> ResumenCiclo:
    """Un ciclo completo con transacciones cortas (reconciliar + generar, y aparte procesar). ``ahora`` con zona (R4)."""
    reconciliados = await _reconciliar(session, ahora)
    generados = await _generar(session, ahora, anticipacion)
    await session.commit()
    pendientes = {i for i, estado in generados if estado == "pendiente"}
    procesados, fallidos = await _procesar(session, ahora, proveedor, pendientes)
    await session.commit()
    resumen = ResumenCiclo(reconciliados=reconciliados, generados=len(generados),
                           sin_telefono=sum(1 for _, e in generados if e == "fallido"), procesados=procesados,
                           fallidos=fallidos)
    if any((resumen.reconciliados, resumen.generados, resumen.procesados)):
        logger.info("recordatorios: reconciliados=%d generados=%d sin_telefono=%d procesados=%d fallidos=%d",
                    resumen.reconciliados, resumen.generados, resumen.sin_telefono, resumen.procesados,
                    resumen.fallidos)
    return resumen
