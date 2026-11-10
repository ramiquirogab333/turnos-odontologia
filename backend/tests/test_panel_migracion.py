"""C-08 (1.1): columna ``turno.origen`` de la migración 007 contra PostgreSQL real. Datos sintéticos (R19)."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.alembic_helpers import alembic

INICIO = datetime(2031, 4, 7, 13, 0, tzinfo=timezone.utc)


async def _turno(s: AsyncSession, ids: dict[str, int], *, inicio: datetime = INICIO,
                 codigo: str | None = None, origen: str | None = None) -> int:
    columnas = "profesional_id, sillon_id, tratamiento_id, inicio, fin, codigo_gestion"
    valores = ":p, :s, :t, :i, :f, :c"
    params = {"p": ids["profesional_id"], "s": ids["sillon_id"], "t": ids["tratamiento_id"],
              "i": inicio, "f": inicio + timedelta(minutes=30), "c": codigo}
    if origen is not None:
        columnas += ", origen"
        valores += ", :o"
        params["o"] = origen
    return int((await s.execute(text(f"INSERT INTO turno ({columnas}) VALUES ({valores}) RETURNING id"),
                                params)).scalar_one())


async def test_origen_es_not_null_con_default_web(session_factory: async_sessionmaker[AsyncSession],
                                                  seed_ids: dict[str, int]) -> None:
    async with session_factory() as s:
        col = (await s.execute(text(
            "SELECT is_nullable, data_type FROM information_schema.columns "
            "WHERE table_name = 'turno' AND column_name = 'origen'"))).one()
        assert (col.is_nullable, col.data_type) == ("NO", "text")
        turno_id = await _turno(s, seed_ids, codigo="codigo-sintetico-01")
        assert (await s.execute(text("SELECT origen FROM turno WHERE id = :i"), {"i": turno_id})).scalar_one() == "web"
        await s.rollback()


@pytest.mark.parametrize("origen", ["web", "manual", "whatsapp"])
async def test_origen_acepta_los_tres_valores(session_factory: async_sessionmaker[AsyncSession],
                                              seed_ids: dict[str, int], origen: str) -> None:
    async with session_factory() as s:
        turno_id = await _turno(s, seed_ids, origen=origen)
        assert (await s.execute(text("SELECT origen FROM turno WHERE id = :i"), {"i": turno_id})).scalar_one() == origen
        await s.rollback()


@pytest.mark.parametrize("origen", ["telefono", "", "WEB"])
async def test_origen_rechaza_valores_fuera_del_check(session_factory: async_sessionmaker[AsyncSession],
                                                      seed_ids: dict[str, int], origen: str) -> None:
    async with session_factory() as s:
        with pytest.raises(IntegrityError):
            await _turno(s, seed_ids, origen=origen)
        await s.rollback()


async def test_backfill_marca_manual_los_turnos_sin_codigo_de_gestion(
        session_factory: async_sessionmaker[AsyncSession], seed_ids: dict[str, int]) -> None:
    try:
        abajo = alembic("downgrade", "006_sena_pagos")
        assert abajo.returncode == 0, abajo.stderr
        async with session_factory() as s:
            assert (await s.execute(text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name = 'turno' AND column_name = 'origen'"))).scalar_one() == 0
            sin_codigo = await _turno_sin_origen(s, seed_ids, INICIO, None)
            con_codigo = await _turno_sin_origen(s, seed_ids, INICIO + timedelta(hours=2), "codigo-sintetico-02")
            await s.commit()
    finally:
        arriba = alembic("upgrade", "head")
        assert arriba.returncode == 0, arriba.stderr
    async with session_factory() as s:
        filas = dict((await s.execute(text(
            "SELECT id, origen FROM turno WHERE id IN (:a, :b)"), {"a": sin_codigo, "b": con_codigo})).all())
    assert filas == {sin_codigo: "manual", con_codigo: "web"}


async def _turno_sin_origen(s: AsyncSession, ids: dict[str, int], inicio: datetime, codigo: str | None) -> int:
    return int((await s.execute(text(
        "INSERT INTO turno (profesional_id, sillon_id, tratamiento_id, inicio, fin, codigo_gestion) "
        "VALUES (:p, :s, :t, :i, :f, :c) RETURNING id"),
        {"p": ids["profesional_id"], "s": ids["sillon_id"], "t": ids["tratamiento_id"], "i": inicio,
         "f": inicio + timedelta(minutes=30), "c": codigo})).scalar_one())
