"""Cierre de caja, anulación, consulta y liquidación (C-12, D3 y D4).

Concurrencia: el cierre, su anulación y toda operación que agregue, quite o cambie un movimiento con fecha (cobros de
presupuesto, devoluciones) toman primero ``pg_advisory_xact_lock(LOCK_CAJA)``. Orden global de locks: ``LOCK_CAJA`` ->
(turno -> pago_sena | presupuesto). Los caminos de C-06 (advisory de reservas -> turno -> pago) no lo toman, así que no
hay ciclo: una acreditación siempre usa ``ahora`` y el margen de 15 minutos del cierre la deja fuera de un día cerrado.
"""

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.caja.calculo import (
    CONCEPTOS_EGRESO,
    CONCEPTOS_INGRESO,
    ORDEN_CONCEPTOS,
    ORDEN_MEDIOS,
    LineaCaja,
    agrupar,
    armar_resumen,
    cerrable_desde,
    comparar,
    dos_decimales,
)
from app.caja.errores import CajaCerradaError, CierreInexistenteError, DiaNoTerminadoError, DiaYaCerradoError
from app.caja.models import CierreCaja, CierreCajaLinea
from app.caja.schemas import (
    CierreDetalleOut,
    CierreOut,
    CierreResumenOut,
    DetalleLiquidacionOut,
    DiferenciaOut,
    LineaCajaOut,
    LiquidacionOut,
    MedioLiquidacionOut,
    RangoFechas,
)
from app.caja.service import cierre_vigente_id, movimientos_del_dia
from app.models.core import Usuario
from app.pacientes.auditoria import auditar
from app.pagos.estados import TransicionInvalidaError
from app.panel.service import zona_clinica

LOCK_CAJA = 5_005_002  # clave arbitraria del advisory lock de la caja (LOCK_RESERVAS = 5_005_001)
SQLSTATE_UNICO = "23505"


async def bloquear_caja(session: AsyncSession) -> None:
    """Serializa cierres, anulaciones y movimientos con fecha; se libera al commit/rollback."""
    await session.execute(select(func.pg_advisory_xact_lock(LOCK_CAJA)))


async def exigir_dia_abierto(session: AsyncSession, instante: datetime) -> None:
    """Un día con cierre vigente no admite movimientos: ``CajaCerradaError(dia)`` (409 ``caja_cerrada``, O2).

    Es la única fuente de la regla: la usan los cobros de presupuesto (registrar y anular) y las devoluciones. El
    caller debe haber tomado ``LOCK_CAJA`` antes, para no competir con un cierre en curso.
    """
    dia = instante.astimezone(zona_clinica()).date()
    if await cierre_vigente_id(session, dia) is not None:
        raise CajaCerradaError(dia)


# --- Lectura -----------------------------------------------------------------------------------------------------

def _resumen(c: CierreCaja, nombre: str | None) -> CierreResumenOut:
    return CierreResumenOut(
        id=c.id, dia=c.dia, estado=c.estado, total_ingresos=c.total_ingresos,  # type: ignore[arg-type]
        total_egresos=c.total_egresos, total_neto=c.total_neto, observaciones=c.observaciones,
        cerrado_por=c.cerrado_por, cerrado_por_nombre=nombre, cerrado_en=c.cerrado_en,
        anulado_por=c.anulado_por, anulado_en=c.anulado_en, anulado_motivo=c.anulado_motivo)


async def _cargar(session: AsyncSession, cierre_id: int) -> tuple[CierreCaja, str | None, list[LineaCaja]]:
    fila = (await session.execute(
        select(CierreCaja, Usuario.nombre_completo).outerjoin(Usuario, Usuario.id == CierreCaja.cerrado_por)
        .where(CierreCaja.id == cierre_id).execution_options(populate_existing=True))).one_or_none()
    if fila is None:
        raise CierreInexistenteError()
    lineas = (await session.execute(select(CierreCajaLinea).where(CierreCajaLinea.cierre_id == cierre_id))).scalars().all()
    return fila[0], fila[1], armar_resumen(LineaCaja(x.concepto, x.medio, x.cantidad, x.total) for x in lineas).lineas


def _lineas_out(lineas: Sequence[LineaCaja]) -> list[LineaCajaOut]:
    return [LineaCajaOut(concepto=x.concepto, medio=x.medio, cantidad=x.cantidad, total=x.total)  # type: ignore[arg-type]
            for x in lineas]


async def leer_cierre(session: AsyncSession, cierre_id: int) -> CierreOut:
    c, nombre, lineas = await _cargar(session, cierre_id)
    return CierreOut(**_resumen(c, nombre).model_dump(), lineas=_lineas_out(lineas))


async def consultar_cierre(session: AsyncSession, cierre_id: int) -> CierreDetalleOut:
    """El cierre con ``cuadra``: sus líneas suman sus totales y coinciden con los movimientos recalculados ahora."""
    c, nombre, lineas = await _cargar(session, cierre_id)
    base = CierreOut(**_resumen(c, nombre).model_dump(), lineas=_lineas_out(lineas))
    if c.estado != "vigente":
        return CierreDetalleOut(**base.model_dump(), cuadra=None, diferencias=[])
    movimientos, _ = await movimientos_del_dia(session, c.dia)
    diferencias = comparar(lineas, agrupar(movimientos).lineas)
    propios = armar_resumen(lineas)
    suman = (propios.total_ingresos, propios.total_egresos, propios.total_neto) == (
        c.total_ingresos, c.total_egresos, c.total_neto)
    return CierreDetalleOut(
        **base.model_dump(), cuadra=suman and not diferencias,
        diferencias=[DiferenciaOut(concepto=d.concepto, medio=d.medio, total_cierre=d.total_cierre,  # type: ignore[arg-type]
                                   total_actual=d.total_actual, cantidad_cierre=d.cantidad_cierre,
                                   cantidad_actual=d.cantidad_actual) for d in diferencias])


async def listar_cierres(session: AsyncSession, rango: RangoFechas) -> list[CierreResumenOut]:
    filas = (await session.execute(
        select(CierreCaja, Usuario.nombre_completo).outerjoin(Usuario, Usuario.id == CierreCaja.cerrado_por)
        .where(CierreCaja.dia >= rango.desde, CierreCaja.dia <= rango.hasta)
        .order_by(CierreCaja.dia.desc(), CierreCaja.id.desc()))).all()
    return [_resumen(c, nombre) for c, nombre in filas]


# --- Escritura ---------------------------------------------------------------------------------------------------

async def cerrar_dia(session: AsyncSession, usuario_id: int, dia: date, observaciones: str | None,
                     ahora: datetime) -> CierreOut:
    """Cierra un día terminado con la foto de sus movimientos. Los importes los calcula el servidor.

    Raises: ``DiaNoTerminadoError`` (antes de las 00:15 del día siguiente), ``DiaYaCerradoError`` (ya hay un vigente).
    """
    desde = cerrable_desde(dia, zona_clinica())
    if ahora < desde:
        raise DiaNoTerminadoError(desde)
    await bloquear_caja(session)
    existente = await cierre_vigente_id(session, dia)
    if existente is not None:
        raise DiaYaCerradoError(existente)
    movimientos, _ = await movimientos_del_dia(session, dia)
    resumen = agrupar(movimientos)
    cierre = CierreCaja(dia=dia, estado="vigente", total_ingresos=resumen.total_ingresos,
                        total_egresos=resumen.total_egresos, total_neto=resumen.total_neto,
                        observaciones=observaciones, cerrado_por=usuario_id, cerrado_en=ahora)
    session.add(cierre)
    try:
        await session.flush()
    except IntegrityError as exc:  # índice único parcial: otro cierre vigente del día (red de seguridad)
        await session.rollback()
        if getattr(getattr(exc, "orig", None), "sqlstate", "") == SQLSTATE_UNICO:
            raise DiaYaCerradoError(await cierre_vigente_id(session, dia) or 0) from exc
        raise
    session.add_all(CierreCajaLinea(cierre_id=cierre.id, concepto=x.concepto, medio=x.medio, cantidad=x.cantidad,
                                    total=x.total) for x in resumen.lineas)
    auditar(session, usuario_id, "cierre_caja", "cierre_caja", cierre.id,
            {"dia": dia.isoformat(), "total_ingresos": f"{resumen.total_ingresos:.2f}",
             "total_egresos": f"{resumen.total_egresos:.2f}", "total_neto": f"{resumen.total_neto:.2f}"})
    cierre_id = cierre.id
    await session.commit()
    return await leer_cierre(session, cierre_id)


async def anular_cierre(session: AsyncSession, usuario_id: int, cierre_id: int, motivo: str,
                        ahora: datetime) -> CierreOut:
    """``vigente -> anulado`` con motivo: el día vuelve a estar abierto. El texto del motivo no se audita (R19).

    Raises: ``CierreInexistenteError`` (404), ``TransicionInvalidaError`` (ya anulado, 409).
    """
    await bloquear_caja(session)
    cierre = (await session.execute(select(CierreCaja).where(CierreCaja.id == cierre_id).with_for_update()
                                    .execution_options(populate_existing=True))).scalar_one_or_none()
    if cierre is None:
        raise CierreInexistenteError()
    if cierre.estado != "vigente":
        raise TransicionInvalidaError(cierre.estado, "anulado")
    cierre.estado = "anulado"
    cierre.anulado_por = usuario_id
    cierre.anulado_en = ahora
    cierre.anulado_motivo = motivo
    auditar(session, usuario_id, "anulacion_cierre_caja", "cierre_caja", cierre.id, {"dia": cierre.dia.isoformat()})
    await session.commit()
    return await leer_cierre(session, cierre_id)


# --- Liquidación (D4) --------------------------------------------------------------------------------------------

async def liquidacion(session: AsyncSession, rango: RangoFechas) -> LiquidacionOut:
    """Consolidado por medio de pago de los cierres vigentes del rango; informa los días sin cierre vigente."""
    cerrados = set((await session.execute(select(CierreCaja.dia).where(
        CierreCaja.estado == "vigente", CierreCaja.dia >= rango.desde, CierreCaja.dia <= rango.hasta))).scalars())
    filas = (await session.execute(
        select(CierreCajaLinea.concepto, CierreCajaLinea.medio, func.sum(CierreCajaLinea.cantidad),
               func.sum(CierreCajaLinea.total))
        .join(CierreCaja, CierreCaja.id == CierreCajaLinea.cierre_id)
        .where(CierreCaja.estado == "vigente", CierreCaja.dia >= rango.desde, CierreCaja.dia <= rango.hasta)
        .group_by(CierreCajaLinea.concepto, CierreCajaLinea.medio))).all()
    por_medio: dict[str, dict[str, tuple[int, Decimal]]] = {}
    for concepto, medio, cantidad, total in filas:
        por_medio.setdefault(medio, {})[concepto] = (int(cantidad), Decimal(total))
    medios: list[MedioLiquidacionOut] = []
    for medio in ORDEN_MEDIOS:
        if medio not in por_medio:
            continue
        conceptos = por_medio[medio]
        ingresos = dos_decimales(sum((t for c, (_, t) in conceptos.items() if c in CONCEPTOS_INGRESO), Decimal("0")))
        egresos = dos_decimales(sum((t for c, (_, t) in conceptos.items() if c in CONCEPTOS_EGRESO), Decimal("0")))
        medios.append(MedioLiquidacionOut(
            medio=medio, ingresos=ingresos, egresos=egresos, neto=dos_decimales(ingresos - egresos),  # type: ignore[arg-type]
            detalle=[DetalleLiquidacionOut(concepto=c, cantidad=conceptos[c][0], total=dos_decimales(conceptos[c][1]))  # type: ignore[arg-type]
                     for c in ORDEN_CONCEPTOS if c in conceptos]))
    total_ingresos = dos_decimales(sum((m.ingresos for m in medios), Decimal("0")))
    total_egresos = dos_decimales(sum((m.egresos for m in medios), Decimal("0")))
    dias = [rango.desde + timedelta(days=i) for i in range((rango.hasta - rango.desde).days + 1)]
    return LiquidacionOut(desde=rango.desde, hasta=rango.hasta, medios=medios, total_ingresos=total_ingresos,
                          total_egresos=total_egresos, total_neto=dos_decimales(total_ingresos - total_egresos),
                          dias_sin_cierre=[d for d in dias if d not in cerrados])
