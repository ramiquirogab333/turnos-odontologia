"""Helpers compartidos de los tests de C-11 (pacientes, ficha, odontograma, presupuestos). Datos sintéticos (R19)."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from itertools import count

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.core import ObraSocial, Paciente, RegistroAuditoria
from tests.conftest import crear_usuario_panel
from tests.panel_helpers import insertar_turno, sembrar_mundo

# Instante fijo del servidor para los tests de la ventana de O16 (el reloj se inyecta con la fixture ``reloj``).
AHORA = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
_dni = count(99500001)  # rango aparte: los tests fijan a mano 99000001, 99000012, etc.


@dataclass
class Escenario:
    """Mundo del panel + una odontóloga (Ana), un odontólogo (Bruno), recepción y admin, con sus tokens."""

    mundo: dict[str, int]
    ana_id: int
    ana: str
    bruno_id: int
    bruno: str
    recepcion_id: int
    recepcion: str
    admin_id: int
    admin: str


async def sembrar_escenario(factory: async_sessionmaker[AsyncSession]) -> Escenario:
    mundo = await sembrar_mundo(factory)
    ana_id, ana = await crear_usuario_panel(factory, "dra.ficticia@turnos.test", ["odontologo"],
                                            profesional_id=mundo["ana"])
    bruno_id, bruno = await crear_usuario_panel(factory, "dr.ficticio@turnos.test", ["odontologo"],
                                                profesional_id=mundo["bruno"])
    recepcion_id, recepcion = await crear_usuario_panel(factory, "recepcion@turnos.test", ["recepcion"])
    admin_id, admin = await crear_usuario_panel(factory, "admin@turnos.test", ["admin"])
    return Escenario(mundo, ana_id, ana, bruno_id, bruno, recepcion_id, recepcion, admin_id, admin)


async def crear_paciente(factory: async_sessionmaker[AsyncSession], *, nombre: str = "Lucía",
                         apellido: str = "Ejemplo", dni: str | None = None, telefono: str = "+5491100000001",
                         email: str | None = "lucia@ejemplo.test", obra_social_id: int | None = None,
                         numero_afiliado: str | None = None) -> int:
    async with factory() as s:
        p = Paciente(nombre=nombre, apellido=apellido, dni=dni or str(next(_dni)), telefono=telefono, email=email,
                     obra_social_id=obra_social_id, numero_afiliado=numero_afiliado)
        s.add(p)
        await s.flush()
        await s.commit()
        return int(p.id)


async def crear_obra_social(factory: async_sessionmaker[AsyncSession], codigo: str = "SWISS",
                            nombre: str = "Swiss Medical", activa: bool = True) -> int:
    async with factory() as s:
        os_ = ObraSocial(codigo=codigo, nombre=nombre, sigla=codigo[:3], is_active=activa)
        s.add(os_)
        await s.flush()
        await s.commit()
        return int(os_.id)


async def turno_de(factory: async_sessionmaker[AsyncSession], esc: Escenario, paciente_id: int | None,
                   inicio: datetime, estado: str = "atendido", prof: str = "ana", **extra: object) -> int:
    """Turno vinculado con el paciente. Los de profesionales distintas pueden coincidir en el tiempo."""
    sillon = "s1" if prof == "ana" else "s2"
    return await insertar_turno(factory, esc.mundo, inicio, estado=estado, prof=prof, sillon=sillon,
                                paciente_id=paciente_id, **extra)  # type: ignore[arg-type]


def hace(dias: int = 0, segundos: int = 0) -> datetime:
    return AHORA - timedelta(days=dias, seconds=segundos)


async def auditorias(factory: async_sessionmaker[AsyncSession], accion: str | None = None) -> list[RegistroAuditoria]:
    async with factory() as s:
        consulta = select(RegistroAuditoria).order_by(RegistroAuditoria.id)
        if accion is not None:
            consulta = consulta.where(RegistroAuditoria.accion == accion)
        return list((await s.execute(consulta)).scalars().all())


async def contar(factory: async_sessionmaker[AsyncSession], tabla: str) -> int:
    async with factory() as s:
        return int((await s.execute(text(f"SELECT count(*) FROM {tabla}"))).scalar_one())  # tabla fija de test


def dinero(valor: str) -> Decimal:
    return Decimal(valor)
