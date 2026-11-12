"""Helpers de los tests de recordatorios (C-09). Datos 100 % sintéticos (R19)."""

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.notificaciones.models import Recordatorio
from app.notificaciones.proveedor import ProveedorManual, ProveedorWhatsApp
from app.notificaciones.service import ResumenCiclo, generar_recordatorios
from app.turnos.models import Turno

# Reloj fijo de los ciclos: martes 17/11/2026 a las 07:00 en la clínica (UTC-3).
AHORA = datetime(2026, 11, 17, 10, 0, tzinfo=timezone.utc)
ANTICIPACION = timedelta(hours=48)


async def ciclo(factory: async_sessionmaker[AsyncSession], *, ahora: datetime = AHORA,
                anticipacion: timedelta = ANTICIPACION, proveedor: ProveedorWhatsApp | None = None) -> ResumenCiclo:
    async with factory() as s:
        return await generar_recordatorios(s, ahora, anticipacion, proveedor or ProveedorManual())


async def recordatorios(factory: async_sessionmaker[AsyncSession], turno_id: int | None = None) -> list[Recordatorio]:
    async with factory() as s:
        consulta = select(Recordatorio).order_by(Recordatorio.id)
        if turno_id is not None:
            consulta = consulta.where(Recordatorio.turno_id == turno_id)
        return list((await s.execute(consulta)).scalars().all())


async def poner_turno(factory: async_sessionmaker[AsyncSession], turno_id: int, **campos: Any) -> None:
    async with factory() as s:
        await s.execute(update(Turno).where(Turno.id == turno_id).values(**campos))
        await s.commit()


async def sembrar_recordatorio(factory: async_sessionmaker[AsyncSession], turno_id: int, turno_inicio: datetime,
                               estado: str = "pendiente", **campos: Any) -> int:
    extra: dict[str, Any] = dict(campos)
    if estado == "enviado":
        extra.setdefault("enviado_en", AHORA - timedelta(hours=1))
    if estado == "confirmado":
        extra.setdefault("confirmado_en", AHORA - timedelta(hours=1))
    if estado in ("fallido", "anulado"):
        extra.setdefault("motivo", "otro" if estado == "fallido" else "turno_cancelado")
    async with factory() as s:
        r = Recordatorio(turno_id=turno_id, estado=estado, turno_inicio=turno_inicio, **extra)
        s.add(r)
        await s.flush()
        await s.commit()
        return int(r.id)
