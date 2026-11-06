"""Servicio de seña y pagos (C-06; R4, R5, R8, R9, R13, R16).

Reglas: RN-SN-01..08, RN-TU-03 (anti-solape), RN-TU-01 (ventana de 24 h), RN-PG-01.

Concurrencia: toda operación que puede cambiar qué turnos bloquean la agenda (reservar, iniciar seña,
acreditar) toma ``pg_advisory_xact_lock(LOCK_RESERVAS)`` ANTES de bloquear filas, siempre en ese orden.
Sin el lock, dos acreditaciones que compiten por el mismo rango violan a la vez el EXCLUDE de
profesional y el de sillón y PostgreSQL aborta una con deadlock (40P01) en lugar de 23P01 (lo
encontró C-05). El EXCLUDE sigue siendo la garantía final en base de datos (R5).
"""

import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import RegistroAuditoria
from app.pagos.calculo import monto_sena, vencimiento
from app.pagos.config import medios_disponibles, obtener_configuracion
from app.pagos.errores import (
    MedioNoHabilitadoError,
    OperacionReintentableError,
    PagoNoAcreditableError,
    PagoNoEncontradoError,
    SenaNoEncontradaError,
    SenaNoRequeridaError,
    TurnoInexistenteError,
    TurnoNoPendienteError,
)
from app.pagos.estados import CancelacionFueraDePlazoError, TransicionInvalidaError, aplicar_transicion
from app.pagos.models import AprobacionPago, ConfiguracionSena, PagoSena
from app.pagos.pasarela import PasarelaNoDisponibleError, PasarelaPagos
from app.public.service import (
    LOCK_RESERVAS,
    ReservaConflictoError,
    _alternativas,
    _cargar_bloqueos,
    _profesional_ocupado,
    _sillon_libre,
    _sillones_activos,
)
from app.shared.logger import get_logger
from app.turnos.models import Profesional, Tratamiento, Turno

logger = get_logger(__name__)
INTENTOS_REFERENCIA = 5


@dataclass(frozen=True)
class ResultadoInicio:
    """Pago activo resultante de iniciar la seña; ``creado`` distingue 201 de 200 (reintento idempotente)."""

    pago: PagoSena
    turno: Turno
    config: ConfiguracionSena
    creado: bool


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


async def _turno_autenticado(session: AsyncSession, turno_id: int, codigo: str | None, *,
                             bloquear: bool = False) -> Turno:
    """Turno cuyo código de gestión coincide (tiempo constante). Cualquier falla es 404 sin pistas."""
    consulta = select(Turno).where(Turno.id == turno_id)
    if bloquear:
        consulta = consulta.with_for_update().execution_options(populate_existing=True)
    turno = (await session.execute(consulta)).scalar_one_or_none()
    if turno is None or not codigo or turno.codigo_gestion is None:
        raise SenaNoEncontradaError()
    if not hmac.compare_digest(turno.codigo_gestion.encode(), codigo.encode()):
        raise SenaNoEncontradaError()
    return turno


async def _bloquear_reservas(session: AsyncSession) -> None:
    """Serializa con reservas y acreditaciones; se libera al commit/rollback."""
    await session.execute(select(func.pg_advisory_xact_lock(LOCK_RESERVAS)))


async def _revalidar_horario(session: AsyncSession, turno: Turno) -> None:
    """RN-TU-03: profesional y algún sillón siguen libres frente a los turnos bloqueantes (409 con alternativas)."""
    bloqueos = await _cargar_bloqueos(session, turno.inicio, turno.fin)
    motivo: str | None = None
    if _profesional_ocupado(bloqueos, turno.profesional_id, turno.inicio, turno.fin):
        motivo = "profesional"
    elif _sillon_libre(await _sillones_activos(session), bloqueos, turno.inicio, turno.fin) is None:
        motivo = "sillon"
    if motivo is None:
        return
    minutos = int((turno.fin - turno.inicio).total_seconds() // 60)
    alternativas = await _alternativas(session, turno.profesional_id, turno.inicio, minutos)
    await session.rollback()
    raise ReservaConflictoError(motivo=motivo, alternativas=alternativas)


async def _pago_pendiente(session: AsyncSession, turno_id: int) -> PagoSena | None:
    return (await session.execute(
        select(PagoSena).where(PagoSena.turno_id == turno_id, PagoSena.estado == "pendiente")
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()


async def _referencia_unica(session: AsyncSession, medio: str, turno_id: int) -> str:
    """MP: uuid hex. Transferencia: código corto para el concepto bancario (``SENA-{id}-XXXXXX``, <= 20)."""
    for _ in range(INTENTOS_REFERENCIA):
        referencia = uuid.uuid4().hex if medio == "mercadopago" else f"SENA-{turno_id}-{secrets.token_hex(3).upper()}"
        existe = (await session.execute(
            select(PagoSena.id).where(PagoSena.referencia_externa == referencia))).first()
        if existe is None:
            return referencia
    raise RuntimeError("No se pudo generar una referencia única")  # pragma: no cover - colisión improbable


async def iniciar_sena(session: AsyncSession, turno_id: int, codigo: str | None, medio: str,
                       pasarela: PasarelaPagos, *, ahora: datetime | None = None) -> ResultadoInicio:
    """Inicia (o reanuda) la seña de un turno ``en_espera`` y confirma la transacción.

    Raises:
        SenaNoEncontradaError: código ausente/ajeno o turno inexistente (404).
        TurnoNoPendienteError: turno no ``en_espera`` o vencido (409 ``estado_invalido``).
        MedioNoHabilitadoError: medio deshabilitado o sin configurar (422).
        ReservaConflictoError: el horario ya lo bloqueó otro turno (409 con alternativas).
        PasarelaNoDisponibleError: la pasarela falló; no queda ningún pago (502).
    """
    ahora = ahora or _ahora()
    await _turno_autenticado(session, turno_id, codigo)
    await _bloquear_reservas(session)
    turno = await _turno_autenticado(session, turno_id, codigo, bloquear=True)
    estado_actual = turno.estado  # leer antes del rollback: expira los atributos
    if estado_actual != "en_espera":
        await session.rollback()
        raise TurnoNoPendienteError(estado_actual)
    if turno.en_espera_vence_en is None or turno.en_espera_vence_en <= ahora:
        await session.rollback()
        raise TurnoNoPendienteError(estado_actual, vencido=True)

    config = await obtener_configuracion(session)
    habilitados = medios_disponibles(config)
    if medio not in habilitados:
        await session.rollback()
        raise MedioNoHabilitadoError(medio, habilitados)

    await _revalidar_horario(session, turno)

    pendiente = await _pago_pendiente(session, turno.id)
    if pendiente is not None and pendiente.medio == medio:
        return ResultadoInicio(pendiente, turno, config, creado=False)

    tratamiento = await session.get(Tratamiento, turno.tratamiento_id)
    assert tratamiento is not None
    monto = monto_sena(tratamiento.precio_base, config.sena_porcentaje)
    if monto <= 0:
        await session.rollback()
        raise SenaNoRequeridaError()

    if pendiente is not None:  # un solo pago activo por turno: el de otro medio queda vencido
        pendiente.estado = "vencido"
        await session.flush()

    if medio == "transferencia":  # RN-SN-07: 24 h (editable), nunca más allá del inicio
        vence_en = vencimiento(ahora, config.expiracion_transferencia_minutos, turno.inicio)
    else:
        vence_en = min(turno.en_espera_vence_en,
                       vencimiento(ahora, config.expiracion_mp_minutos, turno.inicio))
    turno.en_espera_vence_en = vence_en

    pago = PagoSena(
        turno_id=turno.id, medio=medio, monto=monto, porcentaje_aplicado=config.sena_porcentaje,
        estado="pendiente", referencia_externa=await _referencia_unica(session, medio, turno.id),
        vence_en=vence_en)
    session.add(pago)
    await session.flush()

    if medio == "mercadopago":  # antes del commit: si la pasarela falla no queda un pago sin preferencia
        try:
            preferencia = await pasarela.crear_preferencia(
                turno_id=turno.id, referencia_externa=pago.referencia_externa, monto=monto,
                descripcion=f"Seña turno {tratamiento.nombre}", vence_en=vence_en)
        except PasarelaNoDisponibleError:
            await session.rollback()
            raise
        pago.checkout_url = preferencia.checkout_url
    await session.commit()
    return ResultadoInicio(pago, turno, config, creado=True)


async def consultar_sena(session: AsyncSession, turno_id: int, codigo: str | None, *,
                         ahora: datetime | None = None) -> dict[str, Any]:
    """Estado del turno y de su último pago (solo lectura; sin datos de contacto)."""
    ahora = ahora or _ahora()
    turno = await _turno_autenticado(session, turno_id, codigo)
    config = await obtener_configuracion(session)
    pago = (await session.execute(
        select(PagoSena).where(PagoSena.turno_id == turno.id).order_by(PagoSena.id.desc()).limit(1)
    )).scalar_one_or_none()
    tratamiento = await session.get(Tratamiento, turno.tratamiento_id)
    profesional = await session.get(Profesional, turno.profesional_id)
    assert tratamiento is not None and profesional is not None
    monto = pago.monto if pago is not None else monto_sena(tratamiento.precio_base, config.sena_porcentaje)
    en_espera = turno.estado == "en_espera"
    vencida = (en_espera and (turno.en_espera_vence_en is None or turno.en_espera_vence_en <= ahora)) or (
        turno.estado == "cancelado" and (pago is None or pago.estado == "vencido"))
    return {
        "turno": turno, "pago": pago, "config": config, "monto": monto, "vencida": vencida,
        "tratamiento_nombre": tratamiento.nombre, "profesional_nombre": profesional.nombre,
        "vence_en": turno.en_espera_vence_en if en_espera else None,
        "medios_habilitados": medios_disponibles(config),
    }


# ---------------------------------------------------------------------------
# Acreditación (D5): servicio único para el webhook y para el admin
# ---------------------------------------------------------------------------

SQLSTATE_EXCLUSION = "23P01"
SQLSTATE_DEADLOCK = "40P01"
SQLSTATE_SERIALIZACION = "40001"
MAX_REINTENTOS_ACREDITACION = 2


@dataclass(frozen=True)
class ResultadoAcreditacion:
    """Qué pasó: ``acreditado`` (turno reservado), ``a_reembolsar`` (devolución manual) o ``sin_cambios``."""

    efecto: Literal["acreditado", "a_reembolsar", "en_revision", "sin_cambios"]
    pago_id: int
    turno_id: int


def _auditar(session: AsyncSession, *, usuario_id: int | None, accion: str, entidad: str, entidad_id: int,
             antes: dict[str, Any] | None, despues: dict[str, Any]) -> None:
    """Registro de auditoría en la misma transacción (RN-GL-01). Sin PII de contacto."""
    session.add(RegistroAuditoria(
        usuario_id=usuario_id, accion=accion, entidad=entidad, entidad_id=str(entidad_id),
        datos_antes=antes, datos_despues=despues, ip=None))


def _marcar_a_reembolsar(session: AsyncSession, pago: PagoSena, turno: Turno, *, motivo: str,
                         mp_payment_id: str | None, usuario_id: int | None, ahora: datetime,
                         cancelar_turno: bool) -> None:
    """El dinero llegó pero el turno no se puede dar: queda a reembolsar (RN-SN-05) y el turno no se revive."""
    estado_pago_antes = pago.estado
    pago.estado = "a_reembolsar"
    pago.mp_payment_id = mp_payment_id or pago.mp_payment_id
    pago.acreditado_en = ahora
    pago.acreditado_por_usuario_id = usuario_id
    _auditar(session, usuario_id=usuario_id, accion="UPDATE", entidad="pago_sena", entidad_id=pago.id,
             antes={"estado": estado_pago_antes},
             despues={"estado": "a_reembolsar", "turno_id": turno.id, "motivo": motivo, "origen": "sena_a_reembolsar"})
    if cancelar_turno and turno.estado == "en_espera":
        turno.estado = "cancelado"
        _auditar(session, usuario_id=usuario_id, accion="UPDATE", entidad="turno", entidad_id=turno.id,
                 antes={"estado": "en_espera"}, despues={"estado": "cancelado", "motivo": motivo,
                                                         "origen": "sena_a_reembolsar"})


MONEDA_ESPERADA = "ARS"


def _discrepancia(pago: PagoSena, monto_reportado: Decimal | None, moneda_reportada: str | None) -> bool:
    """RN-SN-09 (falla cerrado): el monto o la moneda de la pasarela faltan o no coinciden con la seña.

    El monto se compara con igualdad Decimal exacta y la moneda debe ser ARS.
    """
    if monto_reportado is None or moneda_reportada is None:
        return True
    return monto_reportado != pago.monto or moneda_reportada.upper() != MONEDA_ESPERADA


async def _bloquear_pago_y_turno(session: AsyncSession, pago_id: int) -> tuple[PagoSena, Turno]:
    """Orden de locks único en todo el módulo: advisory (ya tomado) -> turno -> pago_sena (hallazgo 4)."""
    turno_id = (await session.execute(select(PagoSena.turno_id).where(PagoSena.id == pago_id))).scalar_one_or_none()
    if turno_id is None:
        await session.rollback()
        raise PagoNoEncontradoError()
    turno = (await session.execute(
        select(Turno).where(Turno.id == turno_id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one()
    pago = (await session.execute(
        select(PagoSena).where(PagoSena.id == pago_id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one()
    return pago, turno


def _validar_acreditacion_manual(pago: PagoSena, turno: Turno, ahora: datetime) -> None:
    """Re-validación BAJO LOCK de la acreditación de recepción/admin (hallazgo 8).

    Un pago ``en_revision`` (RN-SN-09) se acepta de cualquier medio y ``acreditar_pago`` decide si el turno
    sigue vigente; el resto debe ser una transferencia pendiente y vigente.
    """
    if pago.estado == "en_revision":
        return
    if pago.medio != "transferencia":
        raise PagoNoAcreditableError("no_es_transferencia")
    if pago.estado != "pendiente":
        raise PagoNoAcreditableError("pago_no_pendiente")
    if pago.vence_en <= ahora or turno.estado != "en_espera" or (
            turno.en_espera_vence_en is not None and turno.en_espera_vence_en <= ahora):
        raise PagoNoAcreditableError("vencido")


async def _aprobacion(session: AsyncSession, mp_payment_id: str) -> AprobacionPago | None:
    return (await session.execute(
        select(AprobacionPago).where(AprobacionPago.mp_payment_id == mp_payment_id))).scalar_one_or_none()


def _registrar_aprobacion(session: AsyncSession, pago: PagoSena, mp_payment_id: str | None, estado: str,
                          monto: Decimal | None, moneda: str | None) -> None:
    """Deja constancia de un pago de la pasarela por su id (RN-SN-10)."""
    if mp_payment_id is not None:
        session.add(AprobacionPago(pago_id=pago.id, mp_payment_id=mp_payment_id, estado=estado,
                                   monto_reportado=monto, moneda_reportada=moneda))


async def _cerrar_revisiones(session: AsyncSession, pago_id: int, conservar: str | None) -> list[str]:
    """Pagos ``en_revision`` del pago: el aceptado queda ``aplicado`` y el resto ``a_reembolsar`` (RN-SN-10)."""
    reembolsar: list[str] = []
    for fila in (await session.execute(select(AprobacionPago).where(
            AprobacionPago.pago_id == pago_id, AprobacionPago.estado == "en_revision"))).scalars().all():
        if conservar is not None and fila.mp_payment_id == conservar:
            fila.estado = "aplicado"
        else:
            fila.estado = "a_reembolsar"
            reembolsar.append(fila.mp_payment_id)
    return reembolsar


async def _acreditar_una_vez(session: AsyncSession, pago_id: int, *, mp_payment_id: str | None,
                             usuario_id: int | None, ahora: datetime,
                             forzar_conflicto: bool, monto_reportado: Decimal | None = None,
                             moneda_reportada: str | None = None, manual: bool = False,
                             validar_transferencia: bool = False) -> ResultadoAcreditacion:
    await _bloquear_reservas(session)
    pago, turno = await _bloquear_pago_y_turno(session, pago_id)
    pago_id_, turno_id = pago.id, turno.id

    if validar_transferencia:
        try:
            _validar_acreditacion_manual(pago, turno, ahora)
        except PagoNoAcreditableError:
            await session.rollback()
            raise

    # Idempotencia por id de pago de la pasarela: la misma notificación nunca se aplica dos veces (RN-SN-10).
    if mp_payment_id is not None and await _aprobacion(session, mp_payment_id) is not None:
        await session.rollback()
        return ResultadoAcreditacion("sin_cambios", pago_id_, turno_id)

    if pago.estado in ("acreditado", "a_reembolsar", "no_reembolsado"):
        if manual or mp_payment_id is None:  # reintento de la acreditación manual
            await session.rollback()
            return ResultadoAcreditacion("sin_cambios", pago_id_, turno_id)
        # Otro pago aprobado distinto para una seña ya resuelta: se registra para devolverlo (RN-SN-10).
        _registrar_aprobacion(session, pago, mp_payment_id, "a_reembolsar", monto_reportado, moneda_reportada)
        _auditar(session, usuario_id=usuario_id, accion="UPDATE", entidad="pago_sena", entidad_id=pago.id,
                 antes={"estado": pago.estado},
                 despues={"estado": pago.estado, "turno_id": turno_id, "origen": "sena_pago_excedente",
                          "mp_payment_id": mp_payment_id,
                          "monto_reportado": None if monto_reportado is None else str(monto_reportado)})
        await session.commit()
        return ResultadoAcreditacion("a_reembolsar", pago_id_, turno_id)

    if not manual and _discrepancia(pago, monto_reportado, moneda_reportada):
        antes = pago.estado
        if antes != "en_revision":  # el primer pago discrepante fija el estado y lo informado
            pago.estado = "en_revision"  # no se acredita: el turno sigue en_espera con su vencimiento normal
            pago.mp_payment_id = mp_payment_id or pago.mp_payment_id
            pago.monto_reportado = monto_reportado
            pago.moneda_reportada = moneda_reportada
        _registrar_aprobacion(session, pago, mp_payment_id, "en_revision", monto_reportado, moneda_reportada)
        _auditar(session, usuario_id=usuario_id, accion="UPDATE", entidad="pago_sena", entidad_id=pago.id,
                 antes={"estado": antes},
                 despues={"estado": "en_revision", "turno_id": turno_id, "origen": "sena_en_revision",
                          "monto_esperado": f"{pago.monto:.2f}",
                          "monto_reportado": None if monto_reportado is None else str(monto_reportado),
                          "moneda_reportada": moneda_reportada})
        await session.commit()
        return ResultadoAcreditacion("en_revision", pago_id_, turno_id)

    vigente = turno.estado == "en_espera" and turno.en_espera_vence_en is not None and turno.en_espera_vence_en > ahora
    if not vigente:
        await _cerrar_revisiones(session, pago.id, None)
        _registrar_aprobacion(session, pago, mp_payment_id, "a_reembolsar", monto_reportado, moneda_reportada)
        _marcar_a_reembolsar(session, pago, turno, motivo="turno_no_vigente", mp_payment_id=mp_payment_id,
                             usuario_id=usuario_id, ahora=ahora, cancelar_turno=True)
        await session.commit()
        return ResultadoAcreditacion("a_reembolsar", pago_id_, turno_id)

    bloqueos = await _cargar_bloqueos(session, turno.inicio, turno.fin)
    sillon = None
    if not forzar_conflicto and not _profesional_ocupado(bloqueos, turno.profesional_id, turno.inicio, turno.fin):
        sillon = _sillon_libre(await _sillones_activos(session), bloqueos, turno.inicio, turno.fin,
                               preferido_id=turno.sillon_id)
    if sillon is None:  # el profesional ya está ocupado o no hay sillón: gana el que acreditó primero (RN-TU-03)
        await _cerrar_revisiones(session, pago.id, None)
        _registrar_aprobacion(session, pago, mp_payment_id, "a_reembolsar", monto_reportado, moneda_reportada)
        _marcar_a_reembolsar(session, pago, turno, motivo="horario_ocupado", mp_payment_id=mp_payment_id,
                             usuario_id=usuario_id, ahora=ahora, cancelar_turno=True)
        await session.commit()
        return ResultadoAcreditacion("a_reembolsar", pago_id_, turno_id)

    # Otros pagos pendientes del turno (por ejemplo el de otro medio) pierden vigencia: un solo pago activo.
    for otro in (await session.execute(select(PagoSena).where(
            PagoSena.turno_id == turno.id, PagoSena.id != pago.id, PagoSena.estado == "pendiente"
    ).with_for_update())).scalars().all():
        otro.estado = "vencido"
    if pago.estado in ("vencido", "en_revision"):
        await session.flush()  # libera el índice único de pago activo antes de reactivar este pago

    # El pago aceptado queda aplicado; los pagos en revisión que no son el aceptado se devuelven (RN-SN-10).
    aceptado = mp_payment_id or pago.mp_payment_id
    reembolsar = await _cerrar_revisiones(session, pago.id, aceptado)
    _registrar_aprobacion(session, pago, mp_payment_id, "aplicado", monto_reportado, moneda_reportada)

    sillon_antes = turno.sillon_id
    pago.estado = "acreditado"
    pago.acreditado_en = ahora
    pago.mp_payment_id = aceptado
    pago.acreditado_por_usuario_id = usuario_id
    turno.estado = "reservado"
    turno.en_espera_vence_en = None
    turno.sillon_id = sillon.id
    _auditar(session, usuario_id=usuario_id, accion="UPDATE", entidad="turno", entidad_id=turno.id,
             antes={"estado": "en_espera", "sillon_id": sillon_antes},
             despues={"estado": "reservado", "sillon_id": sillon.id, "origen": "acreditacion_sena",
                      "medio": pago.medio, "pago_id": pago.id, "monto": str(pago.monto),
                      "pagos_a_reembolsar": reembolsar})
    await session.flush()  # los EXCLUDE de la base son la garantía final (R5)
    await session.commit()
    return ResultadoAcreditacion("acreditado", pago_id_, turno_id)


TRANSITORIOS = (SQLSTATE_DEADLOCK, SQLSTATE_SERIALIZACION)


async def acreditar_pago(session: AsyncSession, pago_id: int, *, mp_payment_id: str | None = None,
                         usuario_id: int | None = None, ahora: datetime | None = None,
                         monto_reportado: Decimal | None = None,
                         moneda_reportada: str | None = None, manual: bool = False,
                         validar_transferencia: bool = False) -> ResultadoAcreditacion:
    """Acredita la seña y pasa el turno a ``reservado`` solo si el horario sigue libre. Idempotente por id de pago.

    Si la pasarela informa un monto o una moneda que faltan o no coinciden con la seña (RN-SN-09) el pago pasa a
    ``en_revision`` y NO se acredita; el admin lo resuelve a mano (acreditar) o queda ``a_reembolsar``.
    Solo la acreditación manual (``manual=True``, recepción/admin) no compara. Cada pago de la pasarela se
    registra por su id (RN-SN-10): uno distinto sobre una seña ya resuelta queda ``a_reembolsar``.

    Si el turno ya no está vigente o el horario lo ganó otro, el pago queda ``a_reembolsar`` (P3, RN-SN-05).
    Red de seguridad: ante 23P01 (solape real) o un deadlock/serialización reintenta en una transacción nueva.
    Solo un 23P01 persistente se resuelve como conflicto de agenda (``a_reembolsar``); un deadlock agotado se
    informa como ``OperacionReintentableError`` (503) y NUNCA se traduce en un reembolso.

    Raises:
        PagoNoEncontradoError: el pago no existe.
        PagoNoAcreditableError: con ``validar_transferencia``, el pago ya no es acreditable a mano.
        OperacionReintentableError: deadlock o conflicto transitorio persistente; reintentar más tarde.
    """
    ahora = ahora or _ahora()
    hubo_solape = False
    for intento in range(MAX_REINTENTOS_ACREDITACION + 1):
        ultimo = intento == MAX_REINTENTOS_ACREDITACION
        try:
            return await _acreditar_una_vez(
                session, pago_id, mp_payment_id=mp_payment_id, usuario_id=usuario_id, ahora=ahora,
                forzar_conflicto=ultimo and hubo_solape,
                monto_reportado=monto_reportado, moneda_reportada=moneda_reportada, manual=manual,
                validar_transferencia=validar_transferencia)
        except (IntegrityError, DBAPIError) as exc:
            await session.rollback()
            sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", "")
            if sqlstate == SQLSTATE_EXCLUSION:
                hubo_solape = True
            elif sqlstate not in TRANSITORIOS:
                raise
            logger.warning("acreditacion: %s en el intento %s del pago %s", sqlstate, intento + 1, pago_id)
            if ultimo:
                raise OperacionReintentableError() from exc
    raise OperacionReintentableError()  # pragma: no cover - el bucle siempre retorna o lanza


# ---------------------------------------------------------------------------
# Administración: acreditar transferencias y configuración (RN-SN-08, RN-PG-01)
# ---------------------------------------------------------------------------

async def acreditar_transferencia(session: AsyncSession, pago_id: int, usuario_id: int, *,
                                  ahora: datetime | None = None) -> ResultadoAcreditacion:
    """Acreditación manual por recepción/admin: solo transferencias pendientes y vigentes.

    Raises:
        PagoNoEncontradoError: el pago no existe (404).
        PagoNoAcreditableError: no es transferencia, no está pendiente o venció (409).
    """
    ahora = ahora or _ahora()
    # Medio, estado y vigencia se validan DENTRO de la acreditación, bajo lock (una lectura previa sería vieja).
    return await acreditar_pago(session, pago_id, usuario_id=usuario_id, ahora=ahora, manual=True,
                                validar_transferencia=True)


def _config_a_dict(config: ConfiguracionSena) -> dict[str, Any]:
    """Valores de la configuración serializables a JSONB (dinero como texto)."""
    return {
        "sena_porcentaje": f"{config.sena_porcentaje:.2f}", "medios_habilitados": list(config.medios_habilitados),
        "texto_politica_reembolso": config.texto_politica_reembolso,
        "expiracion_mp_minutos": config.expiracion_mp_minutos,
        "expiracion_transferencia_minutos": config.expiracion_transferencia_minutos,
        "transferencia_alias": config.transferencia_alias, "transferencia_cbu": config.transferencia_cbu,
        "transferencia_titular": config.transferencia_titular,
    }


async def actualizar_configuracion(session: AsyncSession, valores: dict[str, Any],
                                   usuario_id: int) -> ConfiguracionSena:
    """Reemplaza la configuración (ya validada en el borde) y la audita en la misma transacción."""
    config = await obtener_configuracion(session)
    antes = _config_a_dict(config)
    for campo, valor in valores.items():
        setattr(config, campo, valor)
    await session.flush()
    _auditar(session, usuario_id=usuario_id, accion="UPDATE", entidad="configuracion_sena", entidad_id=config.id,
             antes=antes, despues=_config_a_dict(config))
    await session.commit()
    return config


# ---------------------------------------------------------------------------
# Transiciones de estado del turno con efectos sobre la seña (D7)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResultadoCambioEstado:
    """Estado final del turno y, si cambió, el de su seña."""

    turno_id: int
    estado_turno: str
    estado_pago: str | None


async def _cambiar_estado_una_vez(session: AsyncSession, turno_id: int, destino: str, usuario_id: int | None,
                               *, ahora: datetime | None = None) -> ResultadoCambioEstado:
    """Cambia el estado de un turno aplicando la máquina de estados y los efectos sobre la seña.

    - ``ausente`` con seña acreditada -> ``no_reembolsado`` (R9: nunca se reembolsa).
    - ``cancelado`` desde reservado/confirmado con 24 h o más -> seña ``a_reembolsar`` (RN-SN-04).
    - ``en_espera`` -> ``reservado`` NO es manual: la única vía es la acreditación (anti-solape).

    Los endpoints del panel que lo usan son de C-07 y C-08.

    Raises:
        TurnoInexistenteError: el turno no existe.
        TransicionInvalidaError: transición no permitida (409 ``transicion_invalida``).
        CancelacionFueraDePlazoError: faltan menos de 24 h (409 ``fuera_de_plazo``).
    """
    await _bloquear_reservas(session)  # mismo orden en todo el módulo: advisory -> turno -> pago (hallazgo 4)
    turno = (await session.execute(
        select(Turno).where(Turno.id == turno_id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if turno is None:
        await session.rollback()
        raise TurnoInexistenteError()
    actual = turno.estado
    pago = (await session.execute(
        select(PagoSena).where(PagoSena.turno_id == turno.id, PagoSena.estado.in_(("pendiente", "acreditado")))
        .with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    try:
        if actual == "en_espera" and destino == "reservado":
            raise TransicionInvalidaError(actual, destino)
        resultado = aplicar_transicion(actual, destino, estado_pago=pago.estado if pago else None,
                                       inicio=turno.inicio, ahora=ahora)
    except (TransicionInvalidaError, CancelacionFueraDePlazoError):
        await session.rollback()
        raise
    turno.estado = resultado.estado_turno
    if resultado.estado_turno != "en_espera":
        turno.en_espera_vence_en = None
    if pago is not None and resultado.estado_pago is not None:
        pago.estado = resultado.estado_pago
    _auditar(session, usuario_id=usuario_id, accion="UPDATE", entidad="turno", entidad_id=turno.id,
             antes={"estado": actual},
             despues={"estado": destino, "origen": "cambio_estado",
                      "estado_pago": resultado.estado_pago, "pago_id": pago.id if pago else None})
    await session.commit()
    return ResultadoCambioEstado(turno.id, destino, resultado.estado_pago)


async def cambiar_estado_turno(session: AsyncSession, turno_id: int, destino: str, usuario_id: int | None,
                               *, ahora: datetime | None = None) -> ResultadoCambioEstado:
    """Ver ``_cambiar_estado_una_vez``. Reintenta un deadlock/serialización; agotado, ``OperacionReintentableError``."""
    ahora = ahora or _ahora()
    for intento in range(MAX_REINTENTOS_ACREDITACION + 1):
        try:
            return await _cambiar_estado_una_vez(session, turno_id, destino, usuario_id, ahora=ahora)
        except (IntegrityError, DBAPIError) as exc:
            await session.rollback()
            sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", "")
            if sqlstate not in TRANSITORIOS:
                raise
            logger.warning("cambio de estado: %s en el intento %s del turno %s", sqlstate, intento + 1, turno_id)
    raise OperacionReintentableError()
