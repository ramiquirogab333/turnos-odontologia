"""Integración C-05 (2.3): catálogo público de solo lectura para el wizard (PostgreSQL real).

El frontend necesita tratamientos y profesionales para el paso 1 sin autenticación;
los endpoints de catálogo existentes son de panel (`/api/admin/*`, requieren JWT).
Datos 100% sintéticos (R19).
"""

from datetime import time
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.core import Disponibilidad
from app.turnos.models import Profesional, Tratamiento


async def test_tratamientos_publicos_sin_auth_devuelve_nombre_duracion_y_precio(client, seed_ids) -> None:
    r = await client.get("/api/public/tratamientos")
    assert r.status_code == 200, r.text
    assert "authorization" not in r.request.headers
    assert r.json() == [{
        "id": seed_ids["tratamiento_id"], "nombre": "Limpieza", "duracion_minutos": 30, "precio_base": "1000.00",
    }]


async def test_tratamientos_publicos_se_ordenan_por_nombre(client, session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as s:
        s.add_all([
            Tratamiento(nombre="Ortodoncia", duracion_minutos=45, precio_base=Decimal("5000.00")),
            Tratamiento(nombre="Consulta", duracion_minutos=20, precio_base=Decimal("800.00")),
        ])
        await s.commit()
    r = await client.get("/api/public/tratamientos")
    assert [t["nombre"] for t in r.json()] == ["Consulta", "Ortodoncia"]


async def test_tratamientos_publicos_sin_datos_devuelve_lista_vacia(client) -> None:
    r = await client.get("/api/public/tratamientos")
    assert r.status_code == 200 and r.json() == []


async def test_profesionales_publicos_solo_con_franja_vigente_y_sin_matricula(
    client, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as s:
        con = Profesional(nombre="Dra. Sintética", matricula="MAT-9", especialidad="Ortodoncia")
        inactiva = Profesional(nombre="Dr. Inactivo", matricula="MAT-8", especialidad="General")
        sin = Profesional(nombre="Dr. Sin Agenda", matricula="MAT-7", especialidad="General")
        s.add_all([con, inactiva, sin])
        await s.flush()
        s.add_all([
            Disponibilidad(profesional_id=con.id, dia_semana=0, hora_inicio=time(9, 0), hora_fin=time(17, 0)),
            Disponibilidad(profesional_id=inactiva.id, dia_semana=0, hora_inicio=time(9, 0),
                           hora_fin=time(17, 0), is_active=False),
        ])
        await s.commit()
        con_id = int(con.id)
    r = await client.get("/api/public/profesionales")
    assert r.status_code == 200, r.text
    assert r.json() == [{"id": con_id, "nombre": "Dra. Sintética", "especialidad": "Ortodoncia"}]  # sin matrícula


async def test_profesional_con_varias_franjas_aparece_una_sola_vez(
    client, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as s:
        p = Profesional(nombre="Dra. Doble", matricula="MAT-6", especialidad="General")
        s.add(p)
        await s.flush()
        s.add_all([Disponibilidad(profesional_id=p.id, dia_semana=d, hora_inicio=time(9, 0), hora_fin=time(12, 0))
                   for d in (0, 1, 2)])
        await s.commit()
    r = await client.get("/api/public/profesionales")
    assert [x["nombre"] for x in r.json()] == ["Dra. Doble"]
