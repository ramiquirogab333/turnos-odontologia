"""C-09 (2.1-2.4): migración 010_recordatorios y modelo ``Recordatorio`` contra PostgreSQL real. Datos sintéticos (R19)."""

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.alembic_helpers import alembic
from tests.panel_helpers import insertar_turno, sembrar_mundo

INICIO = datetime(2031, 5, 5, 13, 0, tzinfo=timezone.utc)
ENVIO = datetime(2031, 5, 3, 13, 0, tzinfo=timezone.utc)


async def _turno(factory: async_sessionmaker[AsyncSession], inicio: datetime = INICIO) -> int:
    mundo = await sembrar_mundo(factory)
    return await insertar_turno(factory, mundo, inicio)


def _recordatorio(turno_id: int, **campos: Any) -> Any:
    from app.notificaciones.models import Recordatorio

    base: dict[str, Any] = {"turno_id": turno_id, "estado": "pendiente", "turno_inicio": INICIO}
    base.update(campos)
    return Recordatorio(**base)


# --- 2.1 Esquema -------------------------------------------------------------------------------------------------

async def test_los_instantes_son_timestamptz(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as s:
        tipos = {c: d for c, d in (await s.execute(text(
            "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'recordatorio'"))).all()}
    assert tipos, "la tabla recordatorio no existe"
    for col in ("turno_inicio", "generado_en", "enviado_en", "confirmado_en", "proximo_intento_en", "created_at",
                "updated_at"):
        assert tipos[col] == "timestamp with time zone", col


async def test_cada_fk_tiene_un_indice_que_empieza_por_su_columna(
        session_factory: async_sessionmaker[AsyncSession]) -> None:
    """R6: PostgreSQL no indexa las FK solo."""
    async with session_factory() as s:
        fks = {c for (c,) in (await s.execute(text(
            "SELECT a.attname FROM pg_constraint c JOIN pg_attribute a ON a.attrelid = c.conrelid "
            "AND a.attnum = c.conkey[1] WHERE c.contype = 'f' AND c.conrelid = 'recordatorio'::regclass"))).all()}
        sin_indice = {c for (c,) in (await s.execute(text(
            "SELECT a.attname FROM pg_constraint c JOIN pg_attribute a ON a.attrelid = c.conrelid "
            "AND a.attnum = c.conkey[1] WHERE c.contype = 'f' AND c.conrelid = 'recordatorio'::regclass "
            "AND NOT EXISTS (SELECT 1 FROM pg_index i WHERE i.indrelid = c.conrelid "
            "AND i.indkey[0] = c.conkey[1])"))).all()}
    assert {"turno_id", "enviado_por_usuario_id"} <= fks
    assert sin_indice == set()


@pytest.mark.parametrize("campo,valor", [
    ("canal", "sms"),
    ("estado", "perdido"),
    ("motivo", "no_atiende"),
    ("ultimo_error", "e" * 501),
    ("intentos_fallidos", -1),
])
async def test_los_checks_de_dominio_rechazan_valores_fuera_de_catalogo(
        session_factory: async_sessionmaker[AsyncSession], campo: str, valor: object) -> None:
    turno = await _turno(session_factory)
    campos: dict[str, Any] = {campo: valor}
    if campo == "motivo":
        campos["estado"] = "fallido"
    async with session_factory() as s:
        s.add(_recordatorio(turno, **campos))
        with pytest.raises(IntegrityError):
            await s.flush()
        await s.rollback()


@pytest.mark.parametrize("estado,motivo", [("fallido", "sin_telefono"), ("fallido", "numero_invalido"),
                                           ("anulado", "turno_cancelado"), ("anulado", "turno_iniciado")])
async def test_los_motivos_del_catalogo_se_aceptan(session_factory: async_sessionmaker[AsyncSession], estado: str,
                                                   motivo: str) -> None:
    turno = await _turno(session_factory)
    async with session_factory() as s:
        s.add(_recordatorio(turno, estado=estado, motivo=motivo))
        await s.flush()
        await s.rollback()


# --- 2.2 Invariantes por ORM ------------------------------------------------------------------------------------

async def test_dos_recordatorios_no_anulados_del_mismo_turno_e_inicio_se_rechazan(
        session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Inserción duplicada rechazada por la base."""
    turno = await _turno(session_factory)
    async with session_factory() as s:
        s.add(_recordatorio(turno))
        await s.flush()
        s.add(_recordatorio(turno, estado="enviado", enviado_en=ENVIO))
        with pytest.raises(IntegrityError):
            await s.flush()
        await s.rollback()


async def test_uno_anulado_mas_uno_vigente_del_mismo_horario_se_aceptan_y_otro_horario_tambien(
        session_factory: async_sessionmaker[AsyncSession]) -> None:
    turno = await _turno(session_factory)
    async with session_factory() as s:
        s.add(_recordatorio(turno, estado="anulado", motivo="turno_cancelado"))
        s.add(_recordatorio(turno, estado="anulado", motivo="turno_reprogramado"))
        s.add(_recordatorio(turno))
        s.add(_recordatorio(turno, turno_inicio=INICIO + timedelta(days=1)))
        await s.flush()
        await s.rollback()


@pytest.mark.parametrize("campos", [
    {"estado": "confirmado"},  # sin confirmado_en
    {"estado": "pendiente", "confirmado_en": ENVIO},  # confirmado_en sin estado confirmado
    {"estado": "enviado"},  # sin enviado_en
    {"estado": "fallido"},  # sin motivo
    {"estado": "anulado"},  # sin motivo
])
async def test_estados_incoherentes_con_sus_fechas_o_motivos_se_rechazan(
        session_factory: async_sessionmaker[AsyncSession], campos: dict[str, Any]) -> None:
    turno = await _turno(session_factory)
    async with session_factory() as s:
        s.add(_recordatorio(turno, **campos))
        with pytest.raises(IntegrityError):
            await s.flush()
        await s.rollback()


async def test_estados_coherentes_se_aceptan(session_factory: async_sessionmaker[AsyncSession]) -> None:
    turno = await _turno(session_factory)
    async with session_factory() as s:
        s.add(_recordatorio(turno, estado="confirmado", confirmado_en=ENVIO, enviado_en=ENVIO))
        await s.flush()
        await s.rollback()
    async with session_factory() as s:
        s.add(_recordatorio(turno, estado="enviado", enviado_en=ENVIO))
        await s.flush()
        await s.rollback()


async def test_el_modelo_declara_fk_indexadas_y_fechas_con_zona() -> None:
    from sqlalchemy import DateTime

    from app.notificaciones.models import Recordatorio

    indexadas = {c.name for i in Recordatorio.__table__.indexes for c in i.columns}
    assert {"turno_id", "enviado_por_usuario_id"} <= indexadas
    for col in ("turno_inicio", "generado_en", "enviado_en", "confirmado_en", "proximo_intento_en"):
        tipo = Recordatorio.__table__.c[col].type
        assert isinstance(tipo, DateTime) and tipo.timezone is True, col


# --- 2.4 Reversibilidad -----------------------------------------------------------------------------------------

async def test_downgrade_borra_la_tabla_y_sus_indices_y_el_upgrade_vuelve_a_pasar(
        session_factory: async_sessionmaker[AsyncSession]) -> None:
    try:
        abajo = alembic("downgrade", "009_caja_cierres_devol")
        assert abajo.returncode == 0, abajo.stderr
        async with session_factory() as s:
            tabla = (await s.execute(text("SELECT to_regclass('public.recordatorio')"))).scalar_one()
            indices = (await s.execute(text(
                "SELECT count(*) FROM pg_indexes WHERE indexname LIKE '%recordatorio%'"))).scalar_one()
            assert (tabla, indices) == (None, 0)
    finally:
        arriba = alembic("upgrade", "head")
        assert arriba.returncode == 0, arriba.stderr
    async with session_factory() as s:
        assert (await s.execute(text("SELECT to_regclass('public.recordatorio')"))).scalar_one() == "recordatorio"
        assert (await s.execute(text("SELECT version_num FROM alembic_version"))).scalar_one() \
            == "010_recordatorios"
