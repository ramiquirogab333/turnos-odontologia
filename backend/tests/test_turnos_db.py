"""RED (task 4.2): DB-level double-INSERT concurrency + '[)' adjacency."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

BASE = datetime(2030, 5, 6, 10, 0, tzinfo=timezone.utc)
FIN = BASE + timedelta(minutes=30)


async def _insert(session_factory, prof, sill, trat, inicio, fin, estado="reservado"):
    async with session_factory() as s:
        row = (
            await s.execute(
                text(
                    "INSERT INTO turno (profesional_id, sillon_id, tratamiento_id, "
                    "inicio, fin, estado) "
                    "VALUES (:p, :s, :t, :i, :f, :e) RETURNING id"
                ),
                {"p": prof, "s": sill, "t": trat, "i": inicio, "f": fin, "e": estado},
            )
        ).scalar_one()
        await s.commit()
        return int(row)


async def test_doble_insert_mismo_profesional_aborta_23P01(session_factory, seed_pair) -> None:
    from sqlalchemy.exc import DBAPIError

    p, s1, s2, t = seed_pair["p1"], seed_pair["s1"], seed_pair["s2"], seed_pair["t"]
    await _insert(session_factory, p, s1, t, BASE, FIN)
    # Mismo profesional + sillón distinto + rango solapado -> viola EXCLUDE profesional.
    with pytest.raises(DBAPIError) as exc:
        await _insert(
            session_factory, p, s2, t, BASE + timedelta(minutes=15), FIN + timedelta(minutes=15)
        )
    assert getattr(exc.value.orig, "sqlstate", "") == "23P01"


async def test_doble_insert_mismo_sillon_aborta_23P01(session_factory, seed_pair) -> None:
    from sqlalchemy.exc import DBAPIError

    p1, p2, s, t = seed_pair["p1"], seed_pair["p2"], seed_pair["s1"], seed_pair["t"]
    await _insert(session_factory, p1, s, t, BASE, FIN)
    # Mismo sillón + profesional distinto + rango solapado -> viola EXCLUDE sillón.
    with pytest.raises(DBAPIError) as exc:
        await _insert(
            session_factory, p2, s, t, BASE + timedelta(minutes=15), FIN + timedelta(minutes=15)
        )
    assert getattr(exc.value.orig, "sqlstate", "") == "23P01"


async def test_inserts_adyacentes_confirman(session_factory, seed_ids) -> None:
    ids = seed_ids
    a = await _insert(session_factory, ids["profesional_id"], ids["sillon_id"],
                      ids["tratamiento_id"], BASE, FIN)
    b = await _insert(session_factory, ids["profesional_id"], ids["sillon_id"],
                      ids["tratamiento_id"], FIN, FIN + timedelta(minutes=30))
    assert a != b


async def test_insert_concurrente_solo_uno_confirma(session_factory, seed_ids) -> None:
    """Dos INSERTs solapados en transacciones concurrentes: uno confirma, otro aborta 23P01."""
    from sqlalchemy.exc import DBAPIError

    ids = seed_ids

    async def intento():
        try:
            await _insert(
                session_factory, ids["profesional_id"], ids["sillon_id"],
                ids["tratamiento_id"], BASE, FIN,
            )
            return "ok"
        except DBAPIError as e:
            if getattr(e.orig, "sqlstate", "") == "23P01":
                return "23P01"
            raise

    assert sorted(await asyncio.gather(intento(), intento())) == ["23P01", "ok"]


async def test_estado_no_bloqueante_no_colisiona(session_factory, seed_ids) -> None:
    ids = seed_ids
    await _insert(session_factory, ids["profesional_id"], ids["sillon_id"],
                  ids["tratamiento_id"], BASE, FIN, estado="cancelado")
    # Mismo slot sobre un turno cancelado: el EXCLUDE parcial no lo ve -> confirma.
    nuevo = await _insert(session_factory, ids["profesional_id"], ids["sillon_id"],
                          ids["tratamiento_id"], BASE, FIN)
    assert nuevo > 0
