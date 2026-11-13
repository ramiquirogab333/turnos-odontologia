"""C-13 (2.1, D6, O4): migración 013 — la auditoría es de solo agregado, FK RESTRICT, índices y CHECK de IP."""

import os

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tests.alembic_helpers import alembic
from tests.conftest import crear_usuario_panel

Factory = async_sessionmaker[AsyncSession]

INSERT = ("INSERT INTO registro_auditoria (usuario_id, accion, entidad, entidad_id, ip) "
          "VALUES (:u, 'cierre_caja', 'cierre_caja', '1', :ip) RETURNING id")


async def _fila(factory: Factory, usuario_id: int | None, ip: str | None = "192.0.2.10") -> int:
    async with factory() as s:
        fila = (await s.execute(text(INSERT), {"u": usuario_id, "ip": ip})).scalar_one()
        await s.commit()
        return int(fila)


async def test_update_sobre_la_auditoria_falla_con_p0001_y_deja_la_fila_intacta(session_factory: Factory) -> None:
    fila = await _fila(session_factory, None)
    async with session_factory() as s:
        with pytest.raises(DBAPIError) as exc:
            await s.execute(text("UPDATE registro_auditoria SET accion = 'otra_cosa' WHERE id = :i"), {"i": fila})
        assert getattr(exc.value.orig, "sqlstate", None) == "P0001"
        assert "es de solo agregado" in str(exc.value)
    async with session_factory() as s:
        assert (await s.execute(text("SELECT accion FROM registro_auditoria WHERE id = :i"),
                                {"i": fila})).scalar_one() == "cierre_caja"


async def test_delete_sobre_la_auditoria_falla_con_p0001_y_no_borra_nada(session_factory: Factory) -> None:
    await _fila(session_factory, None)
    await _fila(session_factory, None)
    async with session_factory() as s:
        with pytest.raises(DBAPIError) as exc:
            await s.execute(text("DELETE FROM registro_auditoria"))
        assert getattr(exc.value.orig, "sqlstate", None) == "P0001"
    async with session_factory() as s:
        assert (await s.execute(text("SELECT count(*) FROM registro_auditoria"))).scalar_one() == 2


async def test_insert_sigue_permitido_y_truncate_es_la_via_de_mantenimiento(session_factory: Factory) -> None:
    await _fila(session_factory, None)
    async with session_factory() as s:
        await s.execute(text("TRUNCATE registro_auditoria RESTART IDENTITY CASCADE"))
        await s.commit()
        assert (await s.execute(text("SELECT count(*) FROM registro_auditoria"))).scalar_one() == 0


async def test_la_fk_de_usuario_es_restrict_y_su_indice_existe(session_factory: Factory) -> None:
    async with session_factory() as s:
        accion = (await s.execute(text(
            "SELECT confdeltype::text FROM pg_constraint WHERE contype = 'f' "
            "AND conrelid = 'registro_auditoria'::regclass AND confrelid = 'usuario'::regclass"))).scalar_one()
        sin_indice = (await s.execute(text(
            "SELECT count(*) FROM pg_constraint c WHERE c.contype = 'f' AND c.conrelid = 'registro_auditoria'::regclass "
            "AND NOT EXISTS (SELECT 1 FROM pg_index i WHERE i.indrelid = c.conrelid AND i.indkey[0] = c.conkey[1])"
        ))).scalar_one()
    assert accion == "r"  # RESTRICT
    assert sin_indice == 0  # R6


async def test_existe_el_indice_de_historia_por_entidad(session_factory: Factory) -> None:
    async with session_factory() as s:
        definicion = (await s.execute(text(
            "SELECT indexdef FROM pg_indexes WHERE tablename = 'registro_auditoria' "
            "AND indexname = 'ix_registro_auditoria_entidad'"))).scalar_one_or_none()
    assert definicion is not None
    assert "(entidad, entidad_id, created_at DESC)" in definicion


async def test_una_ip_de_46_caracteres_es_rechazada_y_una_de_45_es_valida(session_factory: Factory) -> None:
    await _fila(session_factory, None, "a" * 45)
    with pytest.raises(IntegrityError) as exc:
        await _fila(session_factory, None, "a" * 46)
    assert "ck_auditoria_ip_len" in str(exc.value)


async def test_borrar_un_usuario_con_registros_es_rechazado(session_factory: Factory) -> None:
    uid, _ = await crear_usuario_panel(session_factory, "admin@turnos.test", ["admin"])
    await _fila(session_factory, uid)
    async with session_factory() as s:
        await s.execute(text("DELETE FROM sesion_panel WHERE usuario_id = :u"), {"u": uid})
        await s.execute(text("DELETE FROM usuario_rol WHERE usuario_id = :u"), {"u": uid})
        with pytest.raises(IntegrityError):
            await s.execute(text("DELETE FROM usuario WHERE id = :u"), {"u": uid})


async def test_downgrade_restaura_set_null_y_quita_trigger_indice_y_check_sin_perder_filas(
        session_factory: Factory) -> None:
    uid, _ = await crear_usuario_panel(session_factory, "admin@turnos.test", ["admin"])
    await _fila(session_factory, uid)
    abajo = alembic("downgrade", "-1")
    try:
        assert abajo.returncode == 0, abajo.stderr
        url = os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://turnos:turnos@localhost:5433/turnos")
        engine = create_async_engine(url)
        try:
            async with engine.connect() as c:
                accion = (await c.execute(text(
                    "SELECT confdeltype::text FROM pg_constraint WHERE contype = 'f' "
                    "AND conrelid = 'registro_auditoria'::regclass AND confrelid = 'usuario'::regclass"))).scalar_one()
                trigger = (await c.execute(text(
                    "SELECT count(*) FROM pg_trigger WHERE tgrelid = 'registro_auditoria'::regclass "
                    "AND NOT tgisinternal"))).scalar_one()
                funcion = (await c.execute(text("SELECT to_regproc('registro_auditoria_inmutable')"))).scalar_one()
                indice = (await c.execute(text("SELECT to_regclass('ix_registro_auditoria_entidad')"))).scalar_one()
                check = (await c.execute(text(
                    "SELECT count(*) FROM pg_constraint WHERE conname = 'ck_auditoria_ip_len'"))).scalar_one()
                filas = (await c.execute(text("SELECT count(*) FROM registro_auditoria"))).scalar_one()
        finally:
            await engine.dispose()
        assert (accion, trigger, funcion, indice, check, filas) == ("n", 0, None, None, 0, 1)
    finally:
        arriba = alembic("upgrade", "head")
    assert arriba.returncode == 0, arriba.stderr
    async with session_factory() as s:
        assert (await s.execute(text("SELECT version_num FROM alembic_version"))).scalar_one() == "013_auditoria_exportacion"
