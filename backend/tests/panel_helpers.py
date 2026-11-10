"""Helpers compartidos de los tests del panel (C-08). Datos 100 % sintéticos (R19)."""

import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.core import Disponibilidad
from app.pagos.models import PagoSena
from app.turnos.models import Profesional, Sillon, Tratamiento, Turno

BA = ZoneInfo("America/Argentina/Buenos_Aires")
TELEFONO = "+5491144445555"
LUNES = date(2031, 11, 17)  # lunes


def local(dia: date, hhmm: str) -> datetime:
    return datetime.combine(dia, time.fromisoformat(hhmm), tzinfo=BA)


async def sembrar_mundo(factory: async_sessionmaker[AsyncSession], *, franja: tuple[str, str] = ("09:00", "13:00"),
                        duracion: int = 30) -> dict[str, int]:
    """Dos profesionales, dos sillones activos, un tratamiento y franjas todos los días para las dos."""
    async with factory() as s:
        ana = Profesional(nombre="Dra. Ana Ficticia", matricula="MAT-A", especialidad="General")
        bruno = Profesional(nombre="Dr. Bruno Ejemplo", matricula="MAT-B", especialidad="General")
        s1 = Sillon(nombre="Sillón 1", estado="activo")
        s2 = Sillon(nombre="Sillón 2", estado="activo")
        trat = Tratamiento(nombre="Limpieza dental", duracion_minutos=duracion, precio_base=Decimal("10000.00"))
        s.add_all([ana, bruno, s1, s2, trat])
        await s.flush()
        for prof in (ana, bruno):
            for dia in range(7):
                s.add(Disponibilidad(profesional_id=prof.id, dia_semana=dia, hora_inicio=time.fromisoformat(franja[0]),
                                     hora_fin=time.fromisoformat(franja[1])))
        await s.commit()
        return {"ana": int(ana.id), "bruno": int(bruno.id), "s1": int(s1.id), "s2": int(s2.id),
                "trat": int(trat.id)}


async def insertar_turno(factory: async_sessionmaker[AsyncSession], mundo: dict[str, int], inicio: datetime, *,
                         estado: str = "reservado", prof: str = "ana", sillon: str = "s1", minutos: int = 30,
                         nombre: str | None = "Carlos Sintético", telefono: str | None = TELEFONO,
                         origen: str = "web", vence: datetime | None = None, con_codigo: bool = True) -> int:
    async with factory() as s:
        t = Turno(profesional_id=mundo[prof], sillon_id=mundo[sillon], tratamiento_id=mundo["trat"], inicio=inicio,
                  fin=inicio + timedelta(minutes=minutos), estado=estado, origen=origen,
                  codigo_gestion=str(uuid.uuid4()) if con_codigo else None, contacto_nombre=nombre,
                  contacto_telefono=telefono,
                  en_espera_vence_en=(vence or inicio) if estado == "en_espera" else None)
        s.add(t)
        await s.flush()
        await s.commit()
        return int(t.id)


async def insertar_pago(factory: async_sessionmaker[AsyncSession], turno_id: int, estado: str, *,
                        monto: str = "3000.00", medio: str = "transferencia", vence: datetime | None = None) -> int:
    async with factory() as s:
        p = PagoSena(turno_id=turno_id, medio=medio, monto=Decimal(monto), porcentaje_aplicado=Decimal("30.00"),
                     estado=estado, referencia_externa=f"ref-{uuid.uuid4().hex}",
                     vence_en=vence or datetime(2031, 12, 1, tzinfo=BA),
                     acreditado_en=datetime(2031, 11, 1, tzinfo=BA) if estado in ("acreditado", "no_reembolsado", "a_reembolsar") else None)
        s.add(p)
        await s.flush()
        await s.commit()
        return int(p.id)


async def turno(factory: async_sessionmaker[AsyncSession], turno_id: int) -> Turno:
    async with factory() as s:
        return (await s.execute(select(Turno).where(Turno.id == turno_id))).scalar_one()


async def pagos(factory: async_sessionmaker[AsyncSession], turno_id: int) -> list[PagoSena]:
    async with factory() as s:
        return list((await s.execute(select(PagoSena).where(PagoSena.turno_id == turno_id)
                                     .order_by(PagoSena.id))).scalars().all())


def cuerpo_alta(mundo: dict[str, int], inicio: datetime, **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"profesional_id": mundo["ana"], "tratamiento_id": mundo["trat"],
                            "inicio": inicio.isoformat(), "nombre": "Carlos Sintético", "telefono": TELEFONO}
    base.update(extra)
    return base
