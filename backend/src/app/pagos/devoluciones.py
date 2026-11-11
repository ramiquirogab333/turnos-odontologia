"""Pendientes de la seña (C-12, D5): lista, rechazo de una revisión y registro de devoluciones hechas a mano.

El sistema no devuelve dinero: recepción devuelve por Mercado Pago o el banco y acá deja constancia con la referencia.
Orden de locks: rechazo = advisory de reservas -> turno -> pago (como C-06); devolución de seña = ``LOCK_CAJA`` -> turno
-> pago. El rechazo no necesita ``LOCK_CAJA`` porque su fecha es ``ahora`` (siempre un día abierto).
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.caja.cierres import bloquear_caja, exigir_dia_abierto
from app.caja.schemas import DevolucionOut, PendienteOut, RechazoOut
from app.pacientes.auditoria import auditar
from app.pagos.errores import (
    FechaDevolucionInvalidaError,
    NoEsDevolucionPendienteError,
    NoEstaEnRevisionError,
    OperacionReintentableError,
    PagoNoEncontradoError,
)
from app.pagos.models import AprobacionPago, PagoSena
from app.pagos.service import (
    MAX_REINTENTOS_ACREDITACION,
    TRANSITORIOS,
    _bloquear_pago_y_turno,
    _bloquear_reservas,
    _cerrar_revisiones,
)
from app.shared.logger import get_logger
from app.turnos.models import Turno

logger = get_logger(__name__)


def importe_recibido_de(pago: PagoSena) -> Decimal:
    """Lo que entró: lo informado por la pasarela si no coincidió con la seña, si no el monto (RN-SN-09)."""
    return pago.monto_reportado if pago.monto_reportado is not None else pago.monto


# --- Lista -------------------------------------------------------------------------------------------------------

async def listar_pendientes(session: AsyncSession) -> list[PendienteOut]:
    """Revisiones, señas por devolver y excedentes de Mercado Pago, del más antiguo al más nuevo (D5).

    Un excedente es una aprobación ``a_reembolsar`` cuyo pago de la pasarela es DISTINTO del de su seña: el propio ya
    está cubierto por la devolución de la seña, así cada importe adeudado figura una sola vez.
    """
    pagos = (await session.execute(
        select(PagoSena, Turno.estado).join(Turno, Turno.id == PagoSena.turno_id)
        .where(PagoSena.estado.in_(("en_revision", "a_reembolsar"))))).all()
    excedentes = (await session.execute(
        select(AprobacionPago, PagoSena.turno_id, PagoSena.medio, Turno.estado)
        .join(PagoSena, PagoSena.id == AprobacionPago.pago_id).join(Turno, Turno.id == PagoSena.turno_id)
        .where(AprobacionPago.estado == "a_reembolsar",
               AprobacionPago.mp_payment_id.is_distinct_from(PagoSena.mp_payment_id)))).all()
    items: list[PendienteOut] = []
    for pago, estado_turno in pagos:
        if pago.estado == "en_revision":  # lo que informó la pasarela; si falta, el importe queda a verificar
            importe, a_verificar = pago.monto_reportado, pago.monto_reportado is None
        else:
            importe, a_verificar = importe_recibido_de(pago), False
        items.append(PendienteOut(
            tipo="revision" if pago.estado == "en_revision" else "sena", id=pago.id, pago_id=pago.id,
            turno_id=pago.turno_id, estado_turno=estado_turno, medio=pago.medio,  # type: ignore[arg-type]
            importe=importe, importe_a_verificar=a_verificar, mp_payment_id=pago.mp_payment_id,
            pendiente_desde=pago.updated_at))
    for aprobacion, turno_id, medio, estado_turno in excedentes:
        items.append(PendienteOut(
            tipo="excedente_mp", id=aprobacion.id, pago_id=aprobacion.pago_id, turno_id=turno_id,
            estado_turno=estado_turno, medio=medio, importe=aprobacion.monto_reportado,  # type: ignore[arg-type]
            importe_a_verificar=aprobacion.monto_reportado is None, mp_payment_id=aprobacion.mp_payment_id,
            pendiente_desde=aprobacion.created_at))
    items.sort(key=lambda x: (x.pendiente_desde, x.tipo, x.id))
    return items


# --- Rechazar una revisión ---------------------------------------------------------------------------------------

async def _rechazar_una_vez(session: AsyncSession, usuario_id: int, pago_id: int, ahora: datetime) -> RechazoOut:
    await _bloquear_reservas(session)
    pago, turno = await _bloquear_pago_y_turno(session, pago_id)  # 404 si no existe
    if pago.estado != "en_revision":
        estado = pago.estado
        await session.rollback()
        raise NoEstaEnRevisionError(estado)
    importe = importe_recibido_de(pago)
    pago.estado = "a_reembolsar"
    pago.acreditado_en = ahora  # D2: todo a_reembolsar tiene el instante en que se recibió el dinero
    await _cerrar_revisiones(session, pago.id, None)  # RN-SN-10: ningún pago en revisión queda colgado
    auditar(session, usuario_id, "sena_revision_rechazada", "pago_sena", pago.id,
            {"pago_id": pago.id, "turno_id": turno.id, "importe": f"{importe:.2f}"})
    resultado = RechazoOut(pago_id=pago.id, turno_id=turno.id, estado_pago="a_reembolsar", estado_turno=turno.estado,
                           importe=importe)
    await session.commit()
    return resultado


async def rechazar_revision(session: AsyncSession, usuario_id: int, pago_id: int, ahora: datetime) -> RechazoOut:
    """``en_revision -> a_reembolsar`` sin tocar el turno (O6). Reintenta un deadlock; agotado, 503.

    Raises: ``PagoNoEncontradoError`` (404), ``NoEstaEnRevisionError`` (409), ``OperacionReintentableError`` (503).
    """
    for intento in range(MAX_REINTENTOS_ACREDITACION + 1):
        try:
            return await _rechazar_una_vez(session, usuario_id, pago_id, ahora)
        except (IntegrityError, DBAPIError) as exc:
            await session.rollback()
            if getattr(getattr(exc, "orig", None), "sqlstate", "") not in TRANSITORIOS:
                raise
            logger.warning("rechazo de revisión: transitorio en el intento %s del pago %s", intento + 1, pago_id)
    raise OperacionReintentableError()


# --- Devoluciones ------------------------------------------------------------------------------------------------

def _validar_fecha(fecha: datetime, ahora: datetime, recibido_en: datetime | None) -> None:
    if fecha > ahora:
        raise FechaDevolucionInvalidaError("fecha_futura")
    if recibido_en is not None and fecha < recibido_en:
        raise FechaDevolucionInvalidaError("fecha_anterior_a_la_recepcion")


async def registrar_devolucion_sena(session: AsyncSession, usuario_id: int, pago_id: int, referencia: str,
                                    fecha: datetime | None, ahora: datetime) -> DevolucionOut:
    """``a_reembolsar -> reembolsado`` (final) con quién, cuándo y la referencia. El importe es el recibido.

    Raises: ``PagoNoEncontradoError``, ``NoEsDevolucionPendienteError`` (cualquier estado distinto, R9),
    ``FechaDevolucionInvalidaError``, ``CajaCerradaError`` (la fecha cae en un día cerrado).
    """
    await bloquear_caja(session)
    pago, turno = await _bloquear_pago_y_turno(session, pago_id)
    if pago.estado != "a_reembolsar":
        estado = pago.estado
        await session.rollback()
        raise NoEsDevolucionPendienteError(estado)
    fecha = fecha or ahora
    _validar_fecha(fecha, ahora, pago.acreditado_en)
    await exigir_dia_abierto(session, fecha)
    importe = importe_recibido_de(pago)
    pago.estado = "reembolsado"
    pago.reembolsado_en = fecha
    pago.reembolsado_por_usuario_id = usuario_id
    pago.reembolso_referencia = referencia
    if pago.mp_payment_id is not None:  # el pago propio de la pasarela es el mismo dinero
        for propia in (await session.execute(select(AprobacionPago).where(
                AprobacionPago.pago_id == pago.id, AprobacionPago.mp_payment_id == pago.mp_payment_id,
                AprobacionPago.estado.in_(("a_reembolsar", "en_revision"))).with_for_update())).scalars():
            propia.estado = "reembolsado"
            propia.reembolsado_en, propia.reembolsado_por_usuario_id = fecha, usuario_id
            propia.reembolso_referencia = referencia
    auditar(session, usuario_id, "devolucion_sena_registrada", "pago_sena", pago.id,
            {"pago_id": pago.id, "turno_id": turno.id, "importe": f"{importe:.2f}"})
    resultado = DevolucionOut(id=pago.id, tipo="sena", pago_id=pago.id, turno_id=turno.id, importe=importe,
                              reembolsado_en=fecha, referencia=referencia)
    await session.commit()
    return resultado


async def registrar_devolucion_excedente(session: AsyncSession, usuario_id: int, aprobacion_id: int, referencia: str,
                                         fecha: datetime | None, ahora: datetime) -> DevolucionOut:
    """Devuelve un pago excedente de Mercado Pago: solo cambia la aprobación; no toca seña, turno ni caja (O5).

    Raises: ``PagoNoEncontradoError`` (404), ``NoEsDevolucionPendienteError`` (ya devuelto o no es un excedente),
    ``FechaDevolucionInvalidaError``.
    """
    fila = (await session.execute(
        select(AprobacionPago, PagoSena.turno_id, PagoSena.mp_payment_id)
        .join(PagoSena, PagoSena.id == AprobacionPago.pago_id).where(AprobacionPago.id == aprobacion_id)
        .with_for_update(of=AprobacionPago).execution_options(populate_existing=True))).one_or_none()
    if fila is None:
        await session.rollback()
        raise PagoNoEncontradoError()
    aprobacion, turno_id, mp_de_la_sena = fila
    if aprobacion.estado != "a_reembolsar" or aprobacion.mp_payment_id == mp_de_la_sena:
        estado = aprobacion.estado
        await session.rollback()
        raise NoEsDevolucionPendienteError(estado)
    fecha = fecha or ahora
    _validar_fecha(fecha, ahora, aprobacion.created_at)
    aprobacion.estado = "reembolsado"
    aprobacion.reembolsado_en = fecha
    aprobacion.reembolsado_por_usuario_id = usuario_id
    aprobacion.reembolso_referencia = referencia
    importe = aprobacion.monto_reportado
    auditar(session, usuario_id, "devolucion_excedente_registrada", "pago_sena_aprobacion", aprobacion.id,
            {"pago_id": aprobacion.pago_id, "turno_id": turno_id,
             "importe": None if importe is None else f"{importe:.2f}"})
    resultado = DevolucionOut(id=aprobacion.id, tipo="excedente_mp", pago_id=aprobacion.pago_id, turno_id=turno_id,
                              importe=importe, reembolsado_en=fecha, referencia=referencia)
    await session.commit()
    return resultado
