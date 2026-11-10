"""C-08 (1.6, 1.7, O19): ``atendido`` ocupa la agenda en los EXCLUDE de la 007. Datos sintéticos (R19)."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.alembic_helpers import alembic

INICIO = datetime(2031, 5, 5, 13, 0, tzinfo=timezone.utc)
MIN = timedelta(minutes=30)


async def _turno(s: AsyncSession, ids: dict[str, int], estado: str, *, inicio: datetime = INICIO,
                 profesional: str = "profesional_id", sillon: str = "sillon_id") -> int:
    return int((await s.execute(text(
        "INSERT INTO turno (profesional_id, sillon_id, tratamiento_id, inicio, fin, estado) "
        "VALUES (:p, :s, :t, :i, :f, :e) RETURNING id"),
        {"p": ids[profesional], "s": ids[sillon], "t": ids["tratamiento_id"], "i": inicio,
         "f": inicio + MIN, "e": estado})).scalar_one())


async def _sqlstate_y_mensaje(s: AsyncSession, ids: dict[str, int], estado: str, *, profesional: str = "profesional_id",
                              sillon: str = "sillon_id") -> tuple[str, str]:
    with pytest.raises(DBAPIError) as exc:
        await _turno(s, ids, estado, profesional=profesional, sillon=sillon)
    await s.rollback()
    return str(getattr(exc.value.orig, "sqlstate", "")), str(exc.value.orig)


@pytest.fixture
async def otros(session_factory: async_sessionmaker[AsyncSession], seed_ids: dict[str, int]) -> dict[str, int]:
    """Segundo profesional y segundo sillón: aíslan cuál de los dos EXCLUDE se dispara."""
    async with session_factory() as s:
        p2 = (await s.execute(text(
            "INSERT INTO profesional (nombre, matricula) VALUES ('Dra. Otra', 'MAT-002') RETURNING id"))).scalar_one()
        s2 = (await s.execute(text("INSERT INTO sillon (nombre) VALUES ('S2') RETURNING id"))).scalar_one()
        await s.commit()
    return {**seed_ids, "profesional2_id": int(p2), "sillon2_id": int(s2)}


@pytest.mark.parametrize("estado", ["reservado", "confirmado"])
async def test_un_bloqueante_superpuesto_a_un_atendido_de_la_misma_profesional_falla(
        session_factory: async_sessionmaker[AsyncSession], otros: dict[str, int], estado: str) -> None:
    async with session_factory() as s:
        await _turno(s, otros, "atendido")
        await s.commit()
        sqlstate, mensaje = await _sqlstate_y_mensaje(s, otros, estado, sillon="sillon2_id")
    assert sqlstate == "23P01"
    assert "turno_no_solape_profesional" in mensaje


async def test_un_bloqueante_superpuesto_a_un_atendido_del_mismo_sillon_falla(
        session_factory: async_sessionmaker[AsyncSession], otros: dict[str, int]) -> None:
    async with session_factory() as s:
        await _turno(s, otros, "atendido")
        await s.commit()
        sqlstate, mensaje = await _sqlstate_y_mensaje(s, otros, "reservado", profesional="profesional2_id")
    assert sqlstate == "23P01"
    assert "turno_no_solape_sillon" in mensaje


async def test_un_turno_superpuesto_a_un_ausente_se_acepta(
        session_factory: async_sessionmaker[AsyncSession], otros: dict[str, int]) -> None:
    async with session_factory() as s:
        await _turno(s, otros, "ausente")
        await _turno(s, otros, "reservado")
        await s.commit()


async def test_un_turno_que_empieza_en_el_fin_del_atendido_se_acepta(
        session_factory: async_sessionmaker[AsyncSession], otros: dict[str, int]) -> None:
    async with session_factory() as s:
        await _turno(s, otros, "atendido")
        await _turno(s, otros, "reservado", inicio=INICIO + MIN)  # rango [) : no se pisan
        await s.commit()


@pytest.mark.parametrize("origen", ["reservado", "confirmado"])
async def test_pasar_a_atendido_nunca_choca(session_factory: async_sessionmaker[AsyncSession],
                                            otros: dict[str, int], origen: str) -> None:
    async with session_factory() as s:
        turno_id = await _turno(s, otros, origen)
        await s.commit()
        await s.execute(text("UPDATE turno SET estado = 'atendido' WHERE id = :i"), {"i": turno_id})
        await s.commit()


# --- 1.7: la migración 007 frente a datos existentes -------------------------------------------------

async def _hay_exclude_con_atendido(s: AsyncSession) -> bool:
    definiciones = (await s.execute(text(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conname IN ('turno_no_solape_profesional', 'turno_no_solape_sillon')"))).scalars().all()
    return len(definiciones) == 2 and all("atendido" in d for d in definiciones)


async def test_la_007_aborta_sin_tocar_datos_y_lista_los_ids_si_hay_solapes_con_un_atendido(
        session_factory: async_sessionmaker[AsyncSession], otros: dict[str, int]) -> None:
    try:
        assert alembic("downgrade", "006_sena_pagos").returncode == 0
        async with session_factory() as s:
            assert not await _hay_exclude_con_atendido(s)
            atendido = await _turno(s, otros, "atendido")
            reservado = await _turno(s, otros, "reservado")  # hoy se puede: el EXCLUDE viejo no cubre atendido
            await s.commit()
        arriba = alembic("upgrade", "head")
        assert arriba.returncode != 0
        assert str(atendido) in arriba.stderr and str(reservado) in arriba.stderr
        async with session_factory() as s:
            estados = dict((await s.execute(text("SELECT id, estado FROM turno"))).all())
            assert estados == {atendido: "atendido", reservado: "reservado"}  # datos intactos
            assert not await _hay_exclude_con_atendido(s)
            version = (await s.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
            assert version == "006_sena_pagos"
            await s.execute(text("DELETE FROM turno WHERE id = :i"), {"i": reservado})  # corrección humana
            await s.commit()
        assert alembic("upgrade", "head").returncode == 0
    finally:
        async with session_factory() as s:
            await s.execute(text("DELETE FROM turno"))
            await s.commit()
        assert alembic("upgrade", "head").returncode == 0
    async with session_factory() as s:
        assert await _hay_exclude_con_atendido(s)


async def test_la_007_aplica_sin_conflictos_y_el_downgrade_restaura_el_predicado_de_la_001(
        session_factory: async_sessionmaker[AsyncSession], otros: dict[str, int]) -> None:
    try:
        abajo = alembic("downgrade", "006_sena_pagos")
        assert abajo.returncode == 0, abajo.stderr
        async with session_factory() as s:
            await _turno(s, otros, "atendido")
            await _turno(s, otros, "reservado")  # solape con atendido: vuelve a aceptarse tras el downgrade
            await s.commit()
            assert not await _hay_exclude_con_atendido(s)
            await s.execute(text("DELETE FROM turno"))
            await s.commit()
        arriba = alembic("upgrade", "head")
        assert arriba.returncode == 0, arriba.stderr
        async with session_factory() as s:
            assert await _hay_exclude_con_atendido(s)
            nombres = set((await s.execute(text(
                "SELECT conname FROM pg_constraint WHERE conname LIKE 'turno_no_solape_%'"))).scalars().all())
            assert nombres == {"turno_no_solape_profesional", "turno_no_solape_sillon"}
    finally:
        async with session_factory() as s:
            await s.execute(text("DELETE FROM turno"))
            await s.commit()
        assert alembic("upgrade", "head").returncode == 0
