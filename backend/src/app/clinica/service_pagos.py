"""Servicio de pagos de presupuesto: cobros manuales con tope y anulación sin borrado (C-11, D8; O3, O4, O12).

El ``SELECT … FOR UPDATE`` del presupuesto serializa los registros concurrentes y la anulación del propio presupuesto:
dos cobros simultáneos se evalúan uno después del otro, nunca contra el mismo saldo.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import PermissionContext
from app.caja.cierres import bloquear_caja, exigir_dia_abierto
from app.clinica.errores import (
    FechaCobroFuturaError,
    MontoExcedeSaldoError,
    PagoInexistenteError,
    PresupuestoInexistenteError,
    PresupuestoNoAceptadoError,
    ReferenciaDuplicadaError,
)
from app.clinica.models import PagoPresupuesto, Presupuesto
from app.clinica.schemas import PagoCreate, PagoRegistradoOut, PagosPresupuestoOut
from app.clinica.service_presupuestos import _bloquear, pago_out
from app.models.core import Paciente
from app.pacientes.auditoria import auditar
from app.pacientes.errores import PacienteInexistenteError
from app.pagos.estados import TransicionInvalidaError
from app.panel.service import zona_clinica

CERO = Decimal("0.00")
SQLSTATE_UNICO = "23505"


async def _total_pagado(session: AsyncSession, presupuesto_id: int) -> Decimal:
    return (await session.execute(
        select(func.coalesce(func.sum(PagoPresupuesto.monto), CERO)).where(
            PagoPresupuesto.presupuesto_id == presupuesto_id, PagoPresupuesto.estado == "registrado"))).scalar_one()


async def registrar_pago(session: AsyncSession, usuario_id: int, paciente_id: int, presupuesto_id: int,
                         data: PagoCreate, ahora: datetime) -> PagoRegistradoOut:
    """Raises: ``PresupuestoNoAceptadoError``, ``FechaCobroFuturaError``, ``CajaCerradaError`` (el día de la fecha de
    cobro tiene un cierre vigente, C-12), ``MontoExcedeSaldoError``, ``ReferenciaDuplicadaError`` (más los 404)."""
    await bloquear_caja(session)  # C-12: orden de locks LOCK_CAJA -> presupuesto (nunca al revés)
    p = await _bloquear(session, paciente_id, presupuesto_id)
    if p.estado != "aceptado":
        raise PresupuestoNoAceptadoError(p.estado)
    fecha = data.fecha_cobro or ahora
    if fecha > ahora:
        raise FechaCobroFuturaError()
    await exigir_dia_abierto(session, fecha)
    pagado = await _total_pagado(session, presupuesto_id)
    saldo = p.total_paciente - pagado
    if data.monto > saldo:
        raise MontoExcedeSaldoError(saldo)
    pago = PagoPresupuesto(presupuesto_id=presupuesto_id, medio=data.medio, monto=data.monto, estado="registrado",
                           fecha_cobro=fecha, referencia=data.referencia, registrado_por=usuario_id)
    session.add(pago)
    try:
        await session.flush()
    except IntegrityError as exc:  # índice único parcial (medio, referencia) entre registrados
        await session.rollback()
        if getattr(getattr(exc, "orig", None), "sqlstate", "") == SQLSTATE_UNICO:
            raise ReferenciaDuplicadaError() from exc
        raise
    auditar(session, usuario_id, "registro_pago_presupuesto", "pago_presupuesto", pago.id,
            {"presupuesto_id": presupuesto_id, "paciente_id": paciente_id, "monto": f"{data.monto:.2f}",
             "medio": data.medio})
    await session.commit()
    return PagoRegistradoOut(pago=pago_out(pago), total_pagado=pagado + data.monto, saldo=saldo - data.monto)


async def anular_pago(session: AsyncSession, usuario_id: int, paciente_id: int, presupuesto_id: int, pago_id: int,
                      motivo: str, ahora: datetime) -> PagoRegistradoOut:
    """Raises: ``PagoInexistenteError`` (404), ``TransicionInvalidaError`` (ya anulado, 409), ``CajaCerradaError`` (el
    día del cobro tiene un cierre vigente, C-12: hay que anular antes el cierre)."""
    await bloquear_caja(session)  # C-12: orden de locks LOCK_CAJA -> presupuesto
    p = await _bloquear(session, paciente_id, presupuesto_id)
    fila = (await session.execute(select(PagoPresupuesto.fecha_cobro, PagoPresupuesto.estado).where(
        PagoPresupuesto.id == pago_id, PagoPresupuesto.presupuesto_id == presupuesto_id))).one_or_none()
    if fila is not None and fila.estado == "registrado":
        await exigir_dia_abierto(session, fila.fecha_cobro)
    actualizado = (await session.execute(
        update(PagoPresupuesto).where(PagoPresupuesto.id == pago_id, PagoPresupuesto.presupuesto_id == presupuesto_id,
                                      PagoPresupuesto.estado == "registrado")
        .values(estado="anulado", anulado_por=usuario_id, anulado_en=ahora, anulado_motivo=motivo)
        .returning(PagoPresupuesto.id))).scalar_one_or_none()
    if actualizado is None:
        existente = (await session.execute(select(PagoPresupuesto.estado).where(
            PagoPresupuesto.id == pago_id, PagoPresupuesto.presupuesto_id == presupuesto_id))).scalar_one_or_none()
        if existente is None:
            raise PagoInexistenteError()
        raise TransicionInvalidaError(existente, "anulado")
    auditar(session, usuario_id, "anulacion_pago_presupuesto", "pago_presupuesto", pago_id,
            {"presupuesto_id": presupuesto_id, "paciente_id": paciente_id})
    await session.commit()
    pago = (await session.execute(select(PagoPresupuesto).where(PagoPresupuesto.id == pago_id)
                                  .execution_options(populate_existing=True))).scalar_one()
    pagado = await _total_pagado(session, presupuesto_id)
    return PagoRegistradoOut(pago=pago_out(pago), total_pagado=pagado, saldo=p.total_paciente - pagado)


async def listar_pagos(session: AsyncSession, contexto: PermissionContext, paciente_id: int,
                       presupuesto_id: int) -> PagosPresupuestoOut:
    """Solo recepción y admin (el router corta por rol antes). Audita la lectura."""
    p = await _bloquear_lectura(session, paciente_id, presupuesto_id)
    pagos = (await session.execute(select(PagoPresupuesto).where(PagoPresupuesto.presupuesto_id == presupuesto_id)
                                   .order_by(PagoPresupuesto.id))).scalars().all()
    pagado = sum((x.monto for x in pagos if x.estado == "registrado"), CERO)
    auditar(session, contexto.usuario_id, "lectura_pagos_presupuesto", "pago_presupuesto", paciente_id,
            {"presupuesto_id": presupuesto_id})
    await session.commit()
    return PagosPresupuestoOut(pagos=[pago_out(x) for x in pagos], total_pagado=pagado,
                               saldo=p.total_paciente - pagado)


async def _bloquear_lectura(session: AsyncSession, paciente_id: int, presupuesto_id: int) -> Presupuesto:
    """Igual que ``_bloquear`` pero sin ``FOR UPDATE``: una lectura no debe serializarse con los cobros."""
    if await session.get(Paciente, paciente_id) is None:
        raise PacienteInexistenteError()
    p = (await session.execute(select(Presupuesto).where(
        Presupuesto.id == presupuesto_id, Presupuesto.paciente_id == paciente_id))).scalar_one_or_none()
    if p is None:
        raise PresupuestoInexistenteError()
    return p


# --- Contrato para C-12 (caja) --------------------------------------------------------------------------------

@dataclass(frozen=True)
class TotalDiario:
    dia: date
    medio: str
    total: Decimal


async def resumen_por_dia_y_medio(session: AsyncSession, desde: datetime, hasta: datetime) -> Sequence[TotalDiario]:
    """Pagos ``registrado`` con ``desde <= fecha_cobro < hasta``, agrupados por día (hora de la clínica) y medio.

    Es la consulta que C-12 suma junto con las señas. Filtra por ``fecha_cobro`` (índice propio) e ignora anulados.
    """
    dia = func.date(func.timezone(zona_clinica().key, PagoPresupuesto.fecha_cobro))
    filas = (await session.execute(
        select(dia.label("dia"), PagoPresupuesto.medio, func.sum(PagoPresupuesto.monto))
        .where(PagoPresupuesto.estado == "registrado", PagoPresupuesto.fecha_cobro >= desde,
               PagoPresupuesto.fecha_cobro < hasta)
        .group_by(dia, PagoPresupuesto.medio).order_by(dia, PagoPresupuesto.medio))).all()
    return [TotalDiario(d, m, t) for d, m, t in filas]
