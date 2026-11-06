"""C-06 (1.1/1.3): migración 006_sena_pagos contra PostgreSQL real. Datos sintéticos (R19)."""

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

BACKEND = Path(__file__).resolve().parents[1]
POLITICA = (
    "Si cancelás con 24 h o más de anticipación, te devolvemos la seña. "
    "Si no asistís, la seña no se devuelve."
)
INICIO = datetime(2031, 3, 3, 13, 0, tzinfo=timezone.utc)


async def _turno(s: AsyncSession, ids: dict[str, int], estado: str = "reservado",
                 inicio: datetime = INICIO, vence: datetime | None = None) -> int:
    fila = await s.execute(text(
        "INSERT INTO turno (profesional_id, sillon_id, tratamiento_id, inicio, fin, estado, en_espera_vence_en) "
        "VALUES (:p, :s, :t, :i, :f, :e, :v) RETURNING id"),
        {"p": ids["profesional_id"], "s": ids["sillon_id"], "t": ids["tratamiento_id"],
         "i": inicio, "f": inicio + timedelta(minutes=30), "e": estado, "v": vence})
    return int(fila.scalar_one())


async def _pago(s: AsyncSession, turno_id: int, *, medio: str = "mercadopago", monto: str = "300.00",
                porcentaje: str = "30.00", estado: str = "pendiente", referencia: str = "ref-sintetica-0001",
                mp_payment_id: str | None = None) -> None:
    await s.execute(text(
        "INSERT INTO pago_sena (turno_id, medio, monto, porcentaje_aplicado, estado, referencia_externa, "
        "mp_payment_id, vence_en) VALUES (:t, :m, :mo, :po, :e, :r, :mp, :v)"),
        {"t": turno_id, "m": medio, "mo": monto, "po": porcentaje, "e": estado, "r": referencia,
         "mp": mp_payment_id, "v": INICIO})


async def test_existen_tablas_columna_y_configuracion_por_defecto(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as s:
        tablas = {r[0] for r in await s.execute(text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"))}
        assert {"pago_sena", "configuracion_sena"} <= tablas
        col = (await s.execute(text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = 'turno' AND column_name = 'en_espera_vence_en'"))).scalar_one()
        assert col == "timestamp with time zone"
        cfg = (await s.execute(text(
            "SELECT id, sena_porcentaje, medios_habilitados, expiracion_mp_minutos, "
            "expiracion_transferencia_minutos, texto_politica_reembolso FROM configuracion_sena"))).one()
    assert cfg.id == 1 and str(cfg.sena_porcentaje) == "30.00"
    assert sorted(cfg.medios_habilitados) == ["mercadopago", "transferencia"]
    assert (cfg.expiracion_mp_minutos, cfg.expiracion_transferencia_minutos) == (30, 1440)
    assert cfg.texto_politica_reembolso == POLITICA


@pytest.mark.parametrize("campo,valor", [
    ("sena_porcentaje", "0"), ("sena_porcentaje", "100.01"),
    ("medios_habilitados", "'{efectivo}'"), ("medios_habilitados", "'{}'"),
    ("transferencia_cbu", "'12345'"), ("transferencia_cbu", "'12345678901234567890AB'"),
])
async def test_configuracion_rechaza_valores_invalidos(session_factory: async_sessionmaker[AsyncSession],
                                                       campo: str, valor: str) -> None:
    async with session_factory() as s:
        with pytest.raises(IntegrityError):
            await s.execute(text(f"UPDATE configuracion_sena SET {campo} = {valor}"))
        await s.rollback()


async def test_configuracion_acepta_limites_validos(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as s:
        await s.execute(text("UPDATE configuracion_sena SET sena_porcentaje = 100.00, "
                             "transferencia_cbu = '0123456789012345678901'"))
        await s.rollback()


async def test_checks_de_pago_rechazan_monto_medio_y_acreditado_sin_fecha(
        session_factory: async_sessionmaker[AsyncSession], seed_ids: dict[str, int]) -> None:
    async with session_factory() as s:
        t = await _turno(s, seed_ids)
        for kwargs in (
            {"monto": "0"}, {"monto": "-1"}, {"medio": "efectivo"},
            {"porcentaje": "0"}, {"porcentaje": "100.01"}, {"estado": "acreditado"},
            {"referencia": "corta"},
        ):
            with pytest.raises(IntegrityError):
                async with s.begin_nested():
                    await _pago(s, t, **kwargs)
        await s.rollback()


async def test_turno_en_espera_exige_vencimiento(session_factory: async_sessionmaker[AsyncSession],
                                                 seed_ids: dict[str, int]) -> None:
    async with session_factory() as s:
        with pytest.raises(IntegrityError):
            await _turno(s, seed_ids, estado="en_espera", vence=None)
        await s.rollback()
        await _turno(s, seed_ids, estado="en_espera", vence=INICIO)  # con vencimiento: válido
        await s.rollback()


async def test_referencia_y_mp_payment_id_son_unicos(session_factory: async_sessionmaker[AsyncSession],
                                                     seed_ids: dict[str, int]) -> None:
    async with session_factory() as s:
        t1 = await _turno(s, seed_ids, inicio=INICIO)
        t2 = await _turno(s, seed_ids, inicio=INICIO + timedelta(hours=2))
        await _pago(s, t1, referencia="ref-sintetica-0001", mp_payment_id="mp-1")
        with pytest.raises(IntegrityError):
            async with s.begin_nested():
                await _pago(s, t2, referencia="ref-sintetica-0001")
        with pytest.raises(IntegrityError):
            async with s.begin_nested():
                await _pago(s, t2, referencia="ref-sintetica-0002", mp_payment_id="mp-1")
        await s.rollback()


async def test_un_solo_pago_activo_por_turno(session_factory: async_sessionmaker[AsyncSession],
                                             seed_ids: dict[str, int]) -> None:
    async with session_factory() as s:
        t = await _turno(s, seed_ids)
        await _pago(s, t, referencia="ref-sintetica-0001", estado="vencido")
        await _pago(s, t, referencia="ref-sintetica-0002", estado="pendiente")
        with pytest.raises(IntegrityError):
            async with s.begin_nested():
                await _pago(s, t, referencia="ref-sintetica-0003", estado="pendiente")
        await s.rollback()


async def test_indices_de_fk_existen(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as s:
        nombres = {r[0] for r in await s.execute(text(
            "SELECT indexname FROM pg_indexes WHERE tablename IN ('pago_sena', 'turno')"))}
    assert {"ix_pago_sena_turno", "ix_pago_sena_acreditado_por", "uq_pago_sena_activo",
            "ix_pago_sena_pendiente_vence", "ix_turno_en_espera_vence"} <= nombres


async def test_update_de_en_espera_solapado_a_reservado_falla_con_23p01(
        session_factory: async_sessionmaker[AsyncSession], seed_ids: dict[str, int]) -> None:
    async with session_factory() as s:
        await _turno(s, seed_ids, estado="reservado")
        en_espera = await _turno(s, seed_ids, estado="en_espera", vence=INICIO)  # mismo horario: no bloquea
        await s.commit()
    async with session_factory() as s:
        with pytest.raises(DBAPIError) as exc:
            await s.execute(text("UPDATE turno SET estado = 'reservado', en_espera_vence_en = NULL WHERE id = :i"),
                            {"i": en_espera})
        assert getattr(exc.value.orig, "sqlstate", "") == "23P01"
        await s.rollback()


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    url = os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://turnos:turnos@localhost:5433/turnos")
    entorno = {**os.environ, "DATABASE_URL": url, "PYTHONPATH": str(BACKEND / "src")}
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=entorno,
                          capture_output=True, text=True, timeout=120)


async def test_ciclo_upgrade_downgrade_upgrade_cancela_los_en_espera(
        session_factory: async_sessionmaker[AsyncSession], seed_ids: dict[str, int]) -> None:
    async with session_factory() as s:
        turno_id = await _turno(s, seed_ids, estado="en_espera", vence=INICIO)
        await s.commit()
    try:
        abajo = _alembic("downgrade", "005_reserva_publica")
        assert abajo.returncode == 0, abajo.stderr
        async with session_factory() as s:
            assert (await s.execute(text("SELECT estado FROM turno WHERE id = :i"), {"i": turno_id})).scalar_one() == "cancelado"
            assert (await s.execute(text("SELECT to_regclass('pago_sena')"))).scalar_one() is None
    finally:
        arriba = _alembic("upgrade", "head")
        assert arriba.returncode == 0, arriba.stderr
    async with session_factory() as s:
        assert (await s.execute(text("SELECT count(*) FROM configuracion_sena"))).scalar_one() == 1


async def test_en_revision_y_monto_reportado_son_validos(session_factory: async_sessionmaker[AsyncSession],
                                                         seed_ids: dict[str, int]) -> None:
    async with session_factory() as s:
        t = await _turno(s, seed_ids)
        await _pago(s, t, estado="en_revision", referencia="ref-sintetica-0001")
        await s.execute(text("UPDATE pago_sena SET monto_reportado = 2999.99, moneda_reportada = 'ARS'"))
        with pytest.raises(IntegrityError):
            async with s.begin_nested():
                await s.execute(text("UPDATE pago_sena SET monto_reportado = -1"))
        await s.rollback()


async def test_tabla_de_aprobaciones_por_id_de_pago(session_factory: async_sessionmaker[AsyncSession],
                                                    seed_ids: dict[str, int]) -> None:
    """Hallazgo 2: cada pago de la pasarela se registra por su id (único) con FK indexada (R6)."""
    async with session_factory() as s:
        nombres = {r[0] for r in await s.execute(text("SELECT indexname FROM pg_indexes WHERE tablename = 'pago_sena_aprobacion'"))}
        assert "ix_pago_sena_aprobacion_pago" in nombres
        t = await _turno(s, seed_ids)
        await _pago(s, t)
        pago_id = (await s.execute(text("SELECT id FROM pago_sena"))).scalar_one()
        ins = ("INSERT INTO pago_sena_aprobacion (pago_id, mp_payment_id, estado, monto_reportado) "
               "VALUES (:p, :m, :e, :mo)")
        await s.execute(text(ins), {"p": pago_id, "m": "PAY-1", "e": "aplicado", "mo": "3000.00"})
        for params in ({"p": pago_id, "m": "PAY-1", "e": "aplicado", "mo": "1"},       # id repetido
                       {"p": pago_id, "m": "PAY-2", "e": "inventado", "mo": "1"},      # estado inválido
                       {"p": pago_id, "m": "PAY-3", "e": "aplicado", "mo": "-1"}):     # monto negativo
            with pytest.raises(IntegrityError):
                async with s.begin_nested():
                    await s.execute(text(ins), params)
        await s.rollback()
