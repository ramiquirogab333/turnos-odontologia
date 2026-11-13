"""C-15 (2.1-2.3): migración 012_sesion_panel y modelo SesionPanel contra PostgreSQL real. Datos sintéticos (R19)."""

import os
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tests.alembic_helpers import alembic
from tests.conftest import crear_usuario_panel

Factory = async_sessionmaker[AsyncSession]
AHORA = datetime(2031, 6, 2, 12, 0, tzinfo=timezone.utc)


def _sesion(usuario_id: int, **campos: Any) -> Any:
    from app.models.auth import SesionPanel

    base: dict[str, Any] = {"sid": uuid4(), "usuario_id": usuario_id, "refresh_jti": uuid4(),
                            "creada_en": AHORA, "expira_en": AHORA + timedelta(hours=12)}
    base.update(campos)
    return SesionPanel(**base)


async def _usuario(factory: Factory) -> int:
    return (await crear_usuario_panel(factory, "recepcion@turnos.test", ["recepcion"]))[0]


# --- 2.1 Esquema ---------------------------------------------------------------------------------------------

async def test_esquema_sid_unico_instantes_timestamptz_y_sin_blacklist(session_factory: Factory) -> None:
    async with session_factory() as s:
        columnas = {c: (t, n) for c, t, n in (await s.execute(text(
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
            "WHERE table_name = 'sesion_panel'"))).all()}
        unico = (await s.execute(text(
            "SELECT count(*) FROM pg_index i WHERE i.indrelid = 'sesion_panel'::regclass AND i.indisunique "
            "AND i.indkey[0] = (SELECT attnum FROM pg_attribute WHERE attrelid = 'sesion_panel'::regclass "
            "AND attname = 'sid') AND i.indnatts = 1"))).scalar_one()
        blacklist = (await s.execute(text("SELECT to_regclass('token_blacklist')"))).scalar_one()
    assert columnas["sid"] == ("uuid", "NO")
    assert columnas["refresh_jti"] == ("uuid", "NO")
    for instante in ("creada_en", "expira_en", "renovada_en", "revocada_en"):
        assert columnas[instante][0] == "timestamp with time zone", instante
    assert columnas["expira_en"][1] == "NO" and columnas["revocada_en"][1] == "YES"
    assert unico == 1
    assert blacklist is None


async def test_la_fk_tiene_indice_que_empieza_por_su_columna_y_hay_indice_de_expiracion(session_factory: Factory) -> None:
    """R6 + purga: el prefijo del índice es la FK; la purga recorre ``expira_en``."""
    async with session_factory() as s:
        sin_indice = (await s.execute(text(
            "SELECT a.attname FROM pg_constraint c JOIN pg_attribute a ON a.attrelid = c.conrelid "
            "AND a.attnum = c.conkey[1] WHERE c.contype = 'f' AND c.conrelid = 'sesion_panel'::regclass "
            "AND NOT EXISTS (SELECT 1 FROM pg_index i WHERE i.indrelid = c.conrelid AND i.indkey[0] = c.conkey[1])"
        ))).all()
        fks = (await s.execute(text(
            "SELECT count(*) FROM pg_constraint WHERE contype = 'f' AND conrelid = 'sesion_panel'::regclass"))).scalar_one()
        por_expira = (await s.execute(text(
            "SELECT count(*) FROM pg_index i WHERE i.indrelid = 'sesion_panel'::regclass "
            "AND i.indkey[0] = (SELECT attnum FROM pg_attribute WHERE attrelid = 'sesion_panel'::regclass "
            "AND attname = 'expira_en')"))).scalar_one()
    assert fks == 1 and sin_indice == []
    assert por_expira >= 1


# --- 2.2 Invariantes por ORM ---------------------------------------------------------------------------------

async def test_una_sesion_valida_se_guarda_y_se_lee_con_zona(session_factory: Factory) -> None:
    from app.models.auth import SesionPanel

    uid = await _usuario(session_factory)
    async with session_factory() as s:
        s.add(_sesion(uid, ip_inicio="2001:db8:85a3:0:0:8a2e:370:7334"))
        await s.commit()
    async with session_factory() as s:
        fila = (await s.execute(select(SesionPanel).where(SesionPanel.ip_inicio.is_not(None)))).scalar_one()
    assert fila.expira_en == AHORA + timedelta(hours=12) and fila.expira_en.tzinfo is not None
    assert fila.revocada_en is None and fila.motivo_revocacion is None


@pytest.mark.parametrize("delta", [timedelta(0), timedelta(seconds=-1)])
async def test_expira_en_debe_ser_posterior_a_creada_en(session_factory: Factory, delta: timedelta) -> None:
    uid = await _usuario(session_factory)
    async with session_factory() as s:
        s.add(_sesion(uid, expira_en=AHORA + delta))
        with pytest.raises(IntegrityError):
            await s.commit()


@pytest.mark.parametrize("campos", [
    {"revocada_en": AHORA},
    {"motivo_revocacion": "logout"},
    {"revocada_en": AHORA, "motivo_revocacion": "otro_motivo"},
    {"revocada_en": AHORA, "motivo_revocacion": ""},
])
async def test_revocacion_exige_instante_y_motivo_de_la_lista(session_factory: Factory, campos: dict[str, Any]) -> None:
    uid = await _usuario(session_factory)
    async with session_factory() as s:
        s.add(_sesion(uid, **campos))
        with pytest.raises(IntegrityError):
            await s.commit()


@pytest.mark.parametrize("motivo", ["logout", "usuario_desactivado"])
async def test_revocacion_con_motivo_valido_se_guarda(session_factory: Factory, motivo: str) -> None:
    uid = await _usuario(session_factory)
    async with session_factory() as s:
        s.add(_sesion(uid, revocada_en=AHORA, motivo_revocacion=motivo))
        await s.commit()


async def test_ip_inicio_admite_45_caracteres_y_rechaza_46(session_factory: Factory) -> None:
    uid = await _usuario(session_factory)
    async with session_factory() as s:
        s.add(_sesion(uid, ip_inicio="a" * 45))
        await s.commit()
    async with session_factory() as s:
        s.add(_sesion(uid, ip_inicio="a" * 46))
        with pytest.raises(IntegrityError):
            await s.commit()


async def test_sid_es_unico(session_factory: Factory) -> None:
    uid = await _usuario(session_factory)
    sid = uuid4()
    async with session_factory() as s:
        s.add(_sesion(uid, sid=sid))
        await s.commit()
    async with session_factory() as s:
        s.add(_sesion(uid, sid=sid))
        with pytest.raises(IntegrityError):
            await s.commit()


async def test_borrar_el_usuario_borra_sus_sesiones(session_factory: Factory) -> None:
    from app.models.core import Usuario

    uid = await _usuario(session_factory)
    async with session_factory() as s:
        s.add(_sesion(uid))
        s.add(_sesion(uid))
        await s.commit()
    async with session_factory() as s:
        await s.execute(text("DELETE FROM usuario_rol WHERE usuario_id = :u"), {"u": uid})
        await s.delete(await s.get(Usuario, uid))
        await s.commit()
        assert (await s.execute(text("SELECT count(*) FROM sesion_panel"))).scalar_one() == 0


# --- 2.3 Reversibilidad --------------------------------------------------------------------------------------

async def test_downgrade_recrea_token_blacklist_identica_a_la_003_y_upgrade_vuelve() -> None:
    abajo = alembic("downgrade", "011_google_calendar")
    try:
        assert abajo.returncode == 0, abajo.stderr
        assert "012_sesion_panel" not in alembic("current").stdout
        url = os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://turnos:turnos@localhost:5433/turnos")
        engine = create_async_engine(url)
        try:
            async with engine.connect() as c:
                tablas = (await c.execute(text(
                    "SELECT to_regclass('sesion_panel'), to_regclass('token_blacklist')"))).one()
                columnas = (await c.execute(text(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_name = 'token_blacklist' ORDER BY ordinal_position"))).all()
                indices = {n for (n,) in (await c.execute(text(
                    "SELECT indexname FROM pg_indexes WHERE tablename = 'token_blacklist'"))).all()}
        finally:
            await engine.dispose()
        assert tablas[0] is None and tablas[1] is not None
        assert [x[0] for x in columnas] == ["id", "jti", "created_at", "updated_at", "expires_at"]
        assert dict((c, t) for c, t in columnas)["expires_at"] == "timestamp with time zone"
        assert {"ix_token_blacklist_jti", "ix_token_blacklist_expires_at"} <= indices
    finally:
        arriba = alembic("upgrade", "head")
    assert arriba.returncode == 0, arriba.stderr
