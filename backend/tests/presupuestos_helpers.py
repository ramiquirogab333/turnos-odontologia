"""Helpers de los tests de presupuestos y pagos de presupuesto (C-11). Datos sintéticos (R19)."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from httpx import AsyncClient, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clinica.models import PagoPresupuesto
from app.db.seeds.runner import run_seeds
from app.models.core import Nomenclador, ObraSocial
from app.turnos.models import Tratamiento
from tests.conftest import bearer


async def sembrar_catalogo(factory: async_sessionmaker[AsyncSession]) -> dict[str, int]:
    """Seed real de C-02 (Limpieza 25000, Consulta 15000; Swiss 90 %, Omint 85 %, OSDE 100 %, Particular 0 %)."""
    async with factory() as s:
        await run_seeds(s)
        await s.commit()
    async with factory() as s:
        # sembrar_mundo ya creó "Limpieza dental" (precio de prueba 10000): el seed la reutiliza por nombre, así que
        # se la lleva al precio real del seed (25000) para que los montos del spec valgan.
        await s.execute(update(Tratamiento).where(Tratamiento.nombre == "Limpieza dental").values(
            precio_base=Decimal("25000.00")))
        await s.commit()
    async with factory() as s:
        trats = {t.nombre: int(t.id) for t in (await s.execute(select(Tratamiento))).scalars()}
        oss = {o.codigo: int(o.id) for o in (await s.execute(select(ObraSocial))).scalars()}
    return {"limpieza": trats["Limpieza dental"], "consulta": trats["Consulta odontológica"],
            "swiss": oss["SWISS"], "omint": oss["OMEGA"], "osde": oss["OSDE"], "particular": oss["PARTICULAR"]}


async def tratamiento_sintetico(factory: async_sessionmaker[AsyncSession], nombre: str, precio: str, *,
                                obra_social_id: int | None = None, cobertura: str = "0.00",
                                diferencial: str = "0.00") -> int:
    async with factory() as s:
        t = Tratamiento(nombre=nombre, duracion_minutos=30, precio_base=Decimal(precio))
        s.add(t)
        await s.flush()
        if obra_social_id is not None:
            s.add(Nomenclador(obra_social_id=obra_social_id, tratamiento_id=t.id, codigo_prestacion="SINT-001",
                              cobertura_porcentaje=Decimal(cobertura), arancel_diferencial=Decimal(diferencial)))
        await s.commit()
        return int(t.id)


def lineas(*pares: tuple[int, int]) -> list[dict[str, Any]]:
    return [{"tratamiento_id": t, "cantidad": c} for t, c in pares]


async def crear_presupuesto(client: AsyncClient, token: str, paciente_id: int, *pares: tuple[int, int],
                            **extra: Any) -> Response:
    return await client.post(f"/api/panel/pacientes/{paciente_id}/presupuestos",
                             json={"lineas": lineas(*pares), **extra}, headers=bearer(token))


async def transicionar(client: AsyncClient, token: str, paciente_id: int, presupuesto_id: int, accion: str,
                       **cuerpo: Any) -> Response:
    return await client.post(f"/api/panel/pacientes/{paciente_id}/presupuestos/{presupuesto_id}/{accion}",
                             json=cuerpo, headers=bearer(token))


async def aceptado(client: AsyncClient, token: str, paciente_id: int, *pares: tuple[int, int]) -> int:
    """Crea, presenta y acepta un presupuesto. Devuelve su id."""
    creado = await crear_presupuesto(client, token, paciente_id, *pares)
    assert creado.status_code == 201, creado.text
    pid = int(creado.json()["id"])
    for accion in ("presentar", "aceptar"):
        r = await transicionar(client, token, paciente_id, pid, accion)
        assert r.status_code == 200, r.text
    return pid


async def insertar_pago(factory: async_sessionmaker[AsyncSession], presupuesto_id: int, monto: str,
                        fecha: datetime, medio: str = "transferencia", referencia: str | None = None) -> int:
    async with factory() as s:
        p = PagoPresupuesto(presupuesto_id=presupuesto_id, medio=medio, monto=Decimal(monto), fecha_cobro=fecha,
                            referencia=referencia, estado="registrado")
        s.add(p)
        await s.flush()
        await s.commit()
        return int(p.id)
