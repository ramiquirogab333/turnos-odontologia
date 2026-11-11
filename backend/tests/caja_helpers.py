"""Helpers de los tests de caja, cierres, devoluciones e indicadores (C-12). Datos 100 % sintéticos (R19)."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from itertools import count
from typing import Any

from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.caja.models import CierreCaja
from app.clinica.models import PagoPresupuesto, Presupuesto
from app.models.core import RegistroAuditoria
from app.pagos.models import AprobacionPago, PagoSena
from tests.clinica_helpers import Escenario, crear_paciente
from tests.conftest import bearer
from tests.panel_helpers import BA, insertar_turno, local

DIA = date(2026, 11, 17)
AYER_A_LA_MANANA = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)  # 09:00 en la clínica
_n = count(1)


def en(dia: date, hhmm: str) -> datetime:
    """Instante de la clínica (``America/Argentina/Buenos_Aires``)."""
    return local(dia, hhmm)


async def sena(factory: async_sessionmaker[AsyncSession], esc: Escenario, *, acreditado_en: datetime | None,
               estado: str = "acreditado", monto: str = "3000.00", medio: str = "mercadopago",
               monto_reportado: str | None = None, turno_estado: str = "reservado",
               inicio: datetime | None = None, reembolsado_en: datetime | None = None,
               reembolso_referencia: str | None = None, nombre: str | None = "Lucía Ejemplo",
               telefono: str | None = "+5491100000011", desde: datetime | None = None,
               mp_payment_id: str | None = None) -> tuple[int, int]:
    """Turno + seña con los estados dados, sin pasar por los flujos (el test fija el estado). Devuelve (turno, pago)."""
    i = next(_n)
    inicio = inicio or datetime(2032, 1, 1, 12, 0, tzinfo=timezone.utc) + timedelta(days=i)
    turno_id = await insertar_turno(factory, esc.mundo, inicio, estado=turno_estado, nombre=nombre,
                                    telefono=telefono)
    fechas = {} if desde is None else {"created_at": desde, "updated_at": desde}  # antigüedad del pendiente
    async with factory() as s:
        pago = PagoSena(
            **fechas, mp_payment_id=mp_payment_id, turno_id=turno_id, medio=medio, monto=Decimal(monto), porcentaje_aplicado=Decimal("30.00"),
            estado=estado, referencia_externa=f"ref-sint-{i:05d}-{'x' * 4}", vence_en=inicio,
            monto_reportado=Decimal(monto_reportado) if monto_reportado else None,
            moneda_reportada="ARS" if monto_reportado else None,
            acreditado_en=acreditado_en, reembolsado_en=reembolsado_en,
            reembolso_referencia=reembolso_referencia)
        s.add(pago)
        await s.flush()
        await s.commit()
        return turno_id, int(pago.id)


async def aprobacion(factory: async_sessionmaker[AsyncSession], pago_id: int, mp_payment_id: str,
                     estado: str = "a_reembolsar", monto_reportado: str | None = "3000.00",
                     desde: datetime | None = None) -> int:
    fechas = {} if desde is None else {"created_at": desde}
    async with factory() as s:
        a = AprobacionPago(**fechas, pago_id=pago_id, mp_payment_id=mp_payment_id, estado=estado,
                           monto_reportado=Decimal(monto_reportado) if monto_reportado else None,
                           moneda_reportada="ARS" if monto_reportado else None)
        s.add(a)
        await s.flush()
        await s.commit()
        return int(a.id)


async def cobro(factory: async_sessionmaker[AsyncSession], *, fecha_cobro: datetime, monto: str = "1500.00",
                medio: str = "transferencia", referencia: str | None = None, estado: str = "registrado",
                paciente_id: int | None = None, presupuesto_id: int | None = None) -> tuple[int, int]:
    """Cobro de presupuesto contra un presupuesto aceptado (se crea si no se pasa). Devuelve (presupuesto, pago)."""
    ahora = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
    async with factory() as s:
        if presupuesto_id is None:
            if paciente_id is None:
                paciente_id = await crear_paciente(factory, nombre="Mateo", apellido="Prueba")
            p = Presupuesto(paciente_id=paciente_id, estado="aceptado", subtotal=Decimal("20000.00"),
                            total_paciente=Decimal("20000.00"), presentado_en=ahora, resuelto_en=ahora)
            s.add(p)
            await s.flush()
            presupuesto_id = int(p.id)
        pago = PagoPresupuesto(
            presupuesto_id=presupuesto_id, medio=medio, monto=Decimal(monto), estado=estado, fecha_cobro=fecha_cobro,
            referencia=referencia,
            anulado_en=ahora if estado == "anulado" else None,
            anulado_motivo="error de carga sintetico" if estado == "anulado" else None)
        s.add(pago)
        await s.flush()
        await s.commit()
        return presupuesto_id, int(pago.id)


async def caja(client: AsyncClient, token: str, dia: str | date | None = None) -> Response:
    params = {} if dia is None else {"dia": str(dia)}
    return await client.get("/api/panel/caja", params=params, headers=bearer(token))


def lineas_de(cuerpo: dict[str, Any]) -> dict[tuple[str, str], tuple[int, str]]:
    return {(x["concepto"], x["medio"]): (x["cantidad"], x["total"]) for x in cuerpo["lineas"]}


async def insertar_cierre(factory: async_sessionmaker[AsyncSession], dia: date, *, estado: str = "vigente",
                          ingresos: str = "0.00", egresos: str = "0.00") -> int:
    async with factory() as s:
        c = CierreCaja(dia=dia, estado=estado, total_ingresos=Decimal(ingresos), total_egresos=Decimal(egresos),
                       total_neto=Decimal(ingresos) - Decimal(egresos),
                       anulado_en=datetime(2026, 11, 20, tzinfo=timezone.utc) if estado == "anulado" else None,
                       anulado_motivo="error sintetico" if estado == "anulado" else None)
        s.add(c)
        await s.flush()
        await s.commit()
        return int(c.id)


async def auditoria_de(factory: async_sessionmaker[AsyncSession], accion: str) -> list[RegistroAuditoria]:
    async with factory() as s:
        return list((await s.execute(select(RegistroAuditoria).where(RegistroAuditoria.accion == accion)
                                     .order_by(RegistroAuditoria.id))).scalars().all())


__all__ = ["BA", "DIA", "AYER_A_LA_MANANA", "en", "sena", "aprobacion", "cobro", "caja", "lineas_de",
           "insertar_cierre", "auditoria_de", "bearer"]
