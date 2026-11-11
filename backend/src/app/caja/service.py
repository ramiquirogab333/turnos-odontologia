"""Caja del día (C-12, D2): movimientos de un día de la clínica y su resumen.

Tres consultas ORM (señas recibidas, cobros de presupuesto y devoluciones) y el agrupado en memoria: una clínica
mueve decenas de pagos por día, así que no hay N+1 ni agregados por separado. El día es ``[00:00, 24:00)`` en la zona
de la clínica (O14). Las reglas de qué es ingreso y egreso viven acá y en ``calculo.py``; nada se calcula en el cliente.
"""

from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.caja.calculo import Movimiento, agrupar, limites_del_dia
from app.caja.models import CierreCaja
from app.caja.schemas import CajaOut, LineaCajaOut, MovimientoOut, SenasRetenidasOut
from app.clinica.models import PagoPresupuesto
from app.pacientes.auditoria import auditar
from app.pagos.models import PagoSena
from app.panel.service import zona_clinica

# Estados de una seña cuyo dinero la clínica ya recibió: el ingreso no depende de lo que pase después (D2).
ESTADOS_CON_INGRESO = ("acreditado", "no_reembolsado", "a_reembolsar", "reembolsado")


def importe_recibido():  # type: ignore[no-untyped-def]
    """Lo que entró: lo informado por la pasarela si no coincidió con la seña (RN-SN-09), si no el monto."""
    return func.coalesce(PagoSena.monto_reportado, PagoSena.monto)


async def movimientos_del_dia(session: AsyncSession, dia: date) -> tuple[list[Movimiento], list[Movimiento]]:
    """(movimientos del día, señas retenidas del día): ingresos por señas y cobros y egresos por devoluciones."""
    desde, hasta = limites_del_dia(dia, zona_clinica())
    importe = importe_recibido()

    senas = (await session.execute(
        select(PagoSena.id, PagoSena.turno_id, PagoSena.medio, importe, PagoSena.acreditado_en,
               PagoSena.referencia_externa, PagoSena.estado)
        .where(PagoSena.acreditado_en >= desde, PagoSena.acreditado_en < hasta,
               PagoSena.estado.in_(ESTADOS_CON_INGRESO)))).all()
    cobros = (await session.execute(
        select(PagoPresupuesto.id, PagoPresupuesto.presupuesto_id, PagoPresupuesto.medio, PagoPresupuesto.monto,
               PagoPresupuesto.fecha_cobro, PagoPresupuesto.referencia)
        .where(PagoPresupuesto.estado == "registrado", PagoPresupuesto.fecha_cobro >= desde,
               PagoPresupuesto.fecha_cobro < hasta))).all()
    devoluciones = (await session.execute(
        select(PagoSena.id, PagoSena.turno_id, PagoSena.medio, importe, PagoSena.reembolsado_en,
               PagoSena.reembolso_referencia)
        .where(PagoSena.estado == "reembolsado", PagoSena.reembolsado_en >= desde,
               PagoSena.reembolsado_en < hasta))).all()

    movimientos = (
        [Movimiento("sena", f.medio, f.coalesce, f.acreditado_en, f.referencia_externa, turno_id=f.turno_id,
                    pago_id=f.id) for f in senas]
        + [Movimiento("pago_presupuesto", f.medio, f.monto, f.fecha_cobro, f.referencia,
                      presupuesto_id=f.presupuesto_id, pago_id=f.id) for f in cobros]
        + [Movimiento("devolucion_sena", f.medio, f.coalesce, f.reembolsado_en, f.reembolso_referencia,
                      turno_id=f.turno_id, pago_id=f.id) for f in devoluciones])
    movimientos.sort(key=lambda m: (m.instante, m.concepto, m.pago_id or 0))
    retenidas = [Movimiento("sena", f.medio, f.coalesce, f.acreditado_en, turno_id=f.turno_id, pago_id=f.id)
                 for f in senas if f.estado == "no_reembolsado"]
    return movimientos, retenidas


async def cierre_vigente_id(session: AsyncSession, dia: date) -> int | None:
    """Id del cierre vigente del día (hay a lo sumo uno), o ``None`` si el día está abierto."""
    return (await session.execute(select(CierreCaja.id).where(
        CierreCaja.dia == dia, CierreCaja.estado == "vigente"))).scalar_one_or_none()


async def consultar_caja(session: AsyncSession, usuario_id: int, dia: date) -> CajaOut:
    """Caja de un día con su detalle. Audita la lectura (``lectura_caja``) sin datos personales (RN-GL-01)."""
    movimientos, retenidas = await movimientos_del_dia(session, dia)
    resumen = agrupar(movimientos)
    cierre_id = await cierre_vigente_id(session, dia)
    zona = zona_clinica()
    auditar(session, usuario_id, "lectura_caja", "caja", dia.isoformat(), {"dia": dia.isoformat()})
    await session.commit()
    total_retenido = agrupar(retenidas)
    return CajaOut(
        dia=dia, estado="cerrado" if cierre_id else "abierto", cierre_id=cierre_id,
        lineas=[LineaCajaOut(concepto=x.concepto, medio=x.medio, cantidad=x.cantidad, total=x.total)  # type: ignore[arg-type]
                for x in resumen.lineas],
        total_ingresos=resumen.total_ingresos, total_egresos=resumen.total_egresos, total_neto=resumen.total_neto,
        senas_retenidas=SenasRetenidasOut(cantidad=len(retenidas), total=total_retenido.total_neto),
        movimientos=[MovimientoOut(concepto=m.concepto, medio=m.medio, importe=m.importe,  # type: ignore[arg-type]
                                   hora=m.instante.astimezone(zona), referencia=m.referencia, turno_id=m.turno_id,
                                   presupuesto_id=m.presupuesto_id) for m in movimientos])


def dia_actual(ahora: datetime) -> date:
    """El día de hoy en la zona de la clínica (nunca el de UTC ni el del navegador)."""
    return ahora.astimezone(zona_clinica()).date()
