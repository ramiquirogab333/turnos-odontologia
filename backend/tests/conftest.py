"""Shared fixtures: real PostgreSQL + HTTP client (FK parents via direct SQL, C-04 owns CRUDs)."""

import os
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

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
    """Truncate all tables before each test (child first)."""
    async with session_factory() as session:
        for table in ("turno", "profesional", "sillon", "tratamiento"):
            await session.execute(text(f"TRUNCATE {table} RESTART IDENTITY CASCADE"))
        await session.commit()
    yield


@pytest_asyncio.fixture
async def seed_ids(
    session_factory: async_sessionmaker[AsyncSession], clean_db: None
) -> dict[str, int]:
    """Insert one Profesional/Sillon/Tratamiento via direct SQL; return their ids."""
    async with session_factory() as session:
        prof = (
            await session.execute(
                text(
                    "INSERT INTO profesional (nombre, matricula, especialidad) "
                    "VALUES ('Dra. Test', 'MAT-001', 'General') RETURNING id"
                )
            )
        ).scalar_one()
        sill = (
            await session.execute(
                text("INSERT INTO sillon (nombre, estado) VALUES ('S1', 'activo') RETURNING id")
            )
        ).scalar_one()
        trat = (
            await session.execute(
                text(
                    "INSERT INTO tratamiento (nombre, duracion_minutos, precio_base) "
                    "VALUES ('Limpieza', 30, 1000.00) RETURNING id"
                )
            )
        ).scalar_one()
        await session.commit()
    return {"profesional_id": int(prof), "sillon_id": int(sill), "tratamiento_id": int(trat)}


@pytest_asyncio.fixture
async def seed_pair(
    session_factory: async_sessionmaker[AsyncSession], clean_db: None
) -> dict[str, int]:
    """Two profesionales + two sillones + one tratamiento for cross-resource tests."""
    async with session_factory() as session:
        p1 = (
            await session.execute(
                text(
                    "INSERT INTO profesional (nombre, matricula, especialidad) "
                    "VALUES ('P1', 'M-1', 'G') RETURNING id"
                )
            )
        ).scalar_one()
        p2 = (
            await session.execute(
                text(
                    "INSERT INTO profesional (nombre, matricula, especialidad) "
                    "VALUES ('P2', 'M-2', 'G') RETURNING id"
                )
            )
        ).scalar_one()
        s1 = (
            await session.execute(
                text("INSERT INTO sillon (nombre, estado) VALUES ('S1', 'activo') RETURNING id")
            )
        ).scalar_one()
        s2 = (
            await session.execute(
                text("INSERT INTO sillon (nombre, estado) VALUES ('S2', 'activo') RETURNING id")
            )
        ).scalar_one()
        t = (
            await session.execute(
                text(
                    "INSERT INTO tratamiento (nombre, duracion_minutos, precio_base) "
                    "VALUES ('T', 30, 500.00) RETURNING id"
                )
            )
        ).scalar_one()
        await session.commit()
    return {
        "p1": int(p1),
        "p2": int(p2),
        "s1": int(s1),
        "s2": int(s2),
        "t": int(t),
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
