"""Shared fixtures: real PostgreSQL + HTTP client (FK parents via ORM harness, C-04 owns CRUDs)."""

import os
import sys
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

# El código vive en src/ (layout canónico de la cátedra): exponerlo en sys.path
# para que `from app...` resuelva sin instalar el paquete. Vía estándar mínima
# (alternativa: `pythonpath = src` en pytest.ini; se eligió conftest para que
# también funcione al importar los tests fuera de pytest).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.turnos.models import Profesional, Sillon, Tratamiento

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql+asyncpg://turnos:turnos@localhost:5433/turnos"
)


@pytest_asyncio.fixture(autouse=True)
async def _reset_app_engine() -> AsyncIterator[None]:
    """Drop the app's cached engine so it is rebuilt on the current test loop.

    pytest-asyncio uses a fresh event loop per test while ``app.shared.db``
    caches one global engine; reusing it across loops corrupts asyncpg
    connections ("another operation is in progress").
    """
    from app.shared import db as app_db

    old = app_db._engine
    app_db._engine = None
    app_db._session_factory = None
    if old is not None:
        try:
            await old.dispose()
        except Exception:  # noqa: BLE001 - connections belonged to a dead loop
            pass
    try:
        yield
    finally:
        current = app_db._engine
        app_db._engine = None
        app_db._session_factory = None
        if current is not None:
            try:
                await current.dispose()
            except Exception:  # noqa: BLE001
                pass


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Engine + factory bound to the test database."""
    engine = create_async_engine(TEST_DATABASE_URL, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def clean_db(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[None]:
    """Delete all rows before each test via ORM (child first, R14; fixture harness)."""
    from app.turnos.models import Turno

    async with session_factory() as session:
        for model in (Turno, Profesional, Sillon, Tratamiento):
            await session.execute(delete(model))
        await session.commit()
    yield


@pytest_asyncio.fixture
async def seed_ids(
    session_factory: async_sessionmaker[AsyncSession], clean_db: None
) -> dict[str, int]:
    """Insert one Profesional/Sillon/Tratamiento via ORM (fixture harness); return ids."""
    from decimal import Decimal

    async with session_factory() as session:
        prof = Profesional(nombre="Dra. Test", matricula="MAT-001", especialidad="General")
        sill = Sillon(nombre="S1", estado="activo")
        trat = Tratamiento(nombre="Limpieza", duracion_minutos=30, precio_base=Decimal("1000.00"))
        session.add_all([prof, sill, trat])
        await session.flush()
        await session.commit()
    return {"profesional_id": int(prof.id), "sillon_id": int(sill.id), "tratamiento_id": int(trat.id)}


@pytest_asyncio.fixture
async def seed_pair(
    session_factory: async_sessionmaker[AsyncSession], clean_db: None
) -> dict[str, int]:
    """Two profesionales + two sillones + one tratamiento via ORM (fixture harness)."""
    from decimal import Decimal

    async with session_factory() as session:
        p1 = Profesional(nombre="P1", matricula="M-1", especialidad="G")
        p2 = Profesional(nombre="P2", matricula="M-2", especialidad="G")
        s1 = Sillon(nombre="S1", estado="activo")
        s2 = Sillon(nombre="S2", estado="activo")
        t = Tratamiento(nombre="T", duracion_minutos=30, precio_base=Decimal("500.00"))
        session.add_all([p1, p2, s1, s2, t])
        await session.flush()
        await session.commit()
    return {
        "p1": int(p1.id),
        "p2": int(p2.id),
        "s1": int(s1.id),
        "s2": int(s2.id),
        "t": int(t.id),
    }


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """HTTP client bound to the FastAPI app via ASGI transport."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def future_iso(minutes_ahead: int = 60) -> str:
    """ISO-8601 UTC timestamp `minutes_ahead` in the future."""
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes_ahead)).isoformat()


def past_iso(minutes_back: int = 60) -> str:
    """ISO-8601 UTC timestamp `minutes_back` in the past."""
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_back)).isoformat()
