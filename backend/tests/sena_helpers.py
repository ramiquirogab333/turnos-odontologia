"""Helpers compartidos de los tests de seña (C-06). Datos 100% sintéticos (R19)."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.core import Disponibilidad
from app.pagos.fake import FakePasarela
from app.pagos.models import ConfiguracionSena, PagoSena
from app.pagos.pasarela import PasarelaNoDisponibleError, PreferenciaCreada
from app.turnos.models import Tratamiento, Turno

TZ = ZoneInfo("America/Argentina/Buenos_Aires")
TELEFONO = "+5491144445555"
ALIAS = "clinica.demo.sintetica"
CBU = "0000003100000000000043"
SECRETO_WEBHOOK = "secreto-webhook-sintetico-tests"


class PasarelaEspia(FakePasarela):
    """Pasarela falsa que registra las llamadas y puede simular una caída (sin red)."""

    def __init__(self) -> None:
        super().__init__("http://localhost:5173")
        self.preferencias: list[dict[str, Any]] = []
        self.consultas: list[str] = []
        self.falla_crear = False
        self.falla_obtener = False

    async def crear_preferencia(self, *, turno_id: int, referencia_externa: str, monto: Decimal,
                                descripcion: str, vence_en: datetime) -> PreferenciaCreada:
        if self.falla_crear:
            raise PasarelaNoDisponibleError("simulada")
        self.preferencias.append({"turno_id": turno_id, "referencia": referencia_externa,
                                  "monto": monto, "vence_en": vence_en})
        return await super().crear_preferencia(turno_id=turno_id, referencia_externa=referencia_externa,
                                               monto=monto, descripcion=descripcion, vence_en=vence_en)

    async def obtener_pago(self, payment_id: str):  # type: ignore[no-untyped-def]
        self.consultas.append(payment_id)
        if self.falla_obtener:
            raise PasarelaNoDisponibleError("simulada")
        return await super().obtener_pago(payment_id)


def fecha_laboral(offset: int = 3) -> date:
    d = datetime.now(TZ).date() + timedelta(days=offset)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def local(fecha: date, hhmm: str) -> datetime:
    return datetime.combine(fecha, time.fromisoformat(hhmm), tzinfo=TZ)


async def sembrar_agenda(factory: async_sessionmaker[AsyncSession], ids: dict[str, int], fecha: date,
                         precio: str = "10000.00") -> None:
    """Franja 09:00-17:00 del día y tratamiento con precio base conocido (seña 30% = 3000.00)."""
    async with factory() as s:
        s.add(Disponibilidad(profesional_id=ids["profesional_id"], dia_semana=fecha.weekday(),
                             hora_inicio=time(9, 0), hora_fin=time(17, 0)))
        await s.execute(update(Tratamiento).where(Tratamiento.id == ids["tratamiento_id"])
                        .values(precio_base=Decimal(precio)))
        await s.commit()


async def configurar(factory: async_sessionmaker[AsyncSession], **valores: Any) -> None:
    async with factory() as s:
        await s.execute(update(ConfiguracionSena).values(**valores))
        await s.commit()


async def configurar_transferencia(factory: async_sessionmaker[AsyncSession]) -> None:
    await configurar(factory, transferencia_alias=ALIAS, transferencia_cbu=CBU,
                     transferencia_titular="Clínica Demo Sintética")


async def reservar(client: httpx.AsyncClient, ids: dict[str, int], inicio: datetime,
                   nombre: str = "Carlos Sintético") -> dict[str, Any]:
    """Reserva pública (queda ``en_espera``) y devuelve el JSON de la respuesta 201."""
    r = await client.post("/api/public/turnos", json={
        "nombre": nombre, "telefono": TELEFONO, "tratamiento_id": ids["tratamiento_id"],
        "profesional_id": ids["profesional_id"], "inicio": inicio.isoformat()})
    assert r.status_code == 201, r.text
    return r.json()


def cabecera(reserva: dict[str, Any]) -> dict[str, str]:
    return {"X-Codigo-Gestion": reserva["codigo_gestion"]}


async def iniciar(client: httpx.AsyncClient, reserva: dict[str, Any], medio: str) -> httpx.Response:
    return await client.post(f"/api/public/turnos/{reserva['turno_id']}/sena", json={"medio": medio},
                             headers=cabecera(reserva))


async def turno_de(factory: async_sessionmaker[AsyncSession], turno_id: int) -> Turno:
    async with factory() as s:
        return (await s.execute(select(Turno).where(Turno.id == turno_id))).scalar_one()


async def pagos_de(factory: async_sessionmaker[AsyncSession], turno_id: int) -> list[PagoSena]:
    async with factory() as s:
        return list((await s.execute(
            select(PagoSena).where(PagoSena.turno_id == turno_id).order_by(PagoSena.id))).scalars().all())


async def forzar_vencimiento(factory: async_sessionmaker[AsyncSession], turno_id: int, vence: datetime) -> None:
    async with factory() as s:
        await s.execute(update(Turno).where(Turno.id == turno_id).values(en_espera_vence_en=vence))
        await s.commit()
