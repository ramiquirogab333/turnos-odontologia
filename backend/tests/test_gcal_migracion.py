"""C-10 (2.1-2.4): migración 011_google_calendar y modelos contra PostgreSQL real. Datos sintéticos (R19)."""

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.alembic_helpers import alembic
from tests.gcal_helpers import sembrar_conexion
from tests.panel_helpers import insertar_turno, sembrar_mundo

INICIO = datetime(2031, 5, 5, 13, 0, tzinfo=timezone.utc)
Factory = async_sessionmaker[AsyncSession]
TABLAS = ("gcal_conexion", "evento_calendar", "gcal_conflicto")


# --- 2.1 Esquema -------------------------------------------------------------------------------------------------

async def test_existen_las_tres_tablas_con_instantes_timestamptz(session_factory: Factory) -> None:
    async with session_factory() as s:
        filas = (await s.execute(text(
            "SELECT table_name, column_name, data_type FROM information_schema.columns "
            "WHERE table_name IN ('gcal_conexion', 'evento_calendar', 'gcal_conflicto')"))).all()
    assert {t for t, _, _ in filas} == set(TABLAS)
    instantes = [(t, c, d) for t, c, d in filas if c.endswith("_en") or c in (
        "inicio", "fin", "created_at", "updated_at", "sistema_inicio", "sistema_fin", "google_inicio", "google_fin")]
    assert instantes and all(d == "timestamp with time zone" for _, _, d in instantes), instantes


@pytest.mark.parametrize("tabla", TABLAS)
async def test_cada_fk_tiene_un_indice_que_empieza_por_su_columna(session_factory: Factory, tabla: str) -> None:
    """R6: PostgreSQL no indexa las FK solo."""
    async with session_factory() as s:
        fks = (await s.execute(text(
            "SELECT count(*) FROM pg_constraint WHERE contype = 'f' AND conrelid = CAST(:t AS regclass)"),
            {"t": tabla})).scalar_one()
        sin_indice = (await s.execute(text(
            "SELECT a.attname FROM pg_constraint c JOIN pg_attribute a ON a.attrelid = c.conrelid "
            "AND a.attnum = c.conkey[1] WHERE c.contype = 'f' AND c.conrelid = CAST(:t AS regclass) "
            "AND NOT EXISTS (SELECT 1 FROM pg_index i WHERE i.indrelid = c.conrelid AND i.indkey[0] = c.conkey[1])"),
            {"t": tabla})).all()
    assert fks >= 1 and sin_indice == []


async def test_el_indice_gist_de_franjas_ajenas_existe(session_factory: Factory) -> None:
    async with session_factory() as s:
        definicion = (await s.execute(text(
            "SELECT indexdef FROM pg_indexes WHERE tablename = 'evento_calendar' "
            "AND indexdef ILIKE '%gist%'"))).scalar_one()
    assert "tstzrange" in definicion and "origen" in definicion


# --- 2.2 Invariantes por ORM ------------------------------------------------------------------------------------

def _evento(conexion_id: int, **campos: Any) -> Any:
    from app.integraciones.gcal.models import EventoCalendar

    base: dict[str, Any] = {"conexion_id": conexion_id, "origen": "google", "google_event_id": "evento-ajeno-1",
                            "estado": "sincronizado", "inicio": INICIO, "fin": INICIO + timedelta(hours=1),
                            "ocupa": True}
    base.update(campos)
    return EventoCalendar(**base)


async def _mundo(factory: Factory) -> tuple[dict[str, int], int, int]:
    mundo = await sembrar_mundo(factory)
    conexion = await sembrar_conexion(factory, mundo["ana"])
    turno = await insertar_turno(factory, mundo, INICIO)
    return mundo, conexion, turno


async def _rechaza(factory: Factory, *objetos: Any) -> None:
    async with factory() as s:
        s.add_all(objetos)
        with pytest.raises(IntegrityError):
            await s.flush()
        await s.rollback()


async def test_una_segunda_conexion_de_la_misma_profesional_se_rechaza(session_factory: Factory) -> None:
    from app.integraciones.gcal.models import GcalConexion

    mundo, _, _ = await _mundo(session_factory)
    await _rechaza(session_factory, GcalConexion(profesional_id=mundo["ana"], estado="desconectada"))


async def test_una_conexion_activa_sin_refresh_token_se_rechaza(session_factory: Factory) -> None:
    from app.integraciones.gcal.models import GcalConexion

    mundo = await sembrar_mundo(session_factory)
    await _rechaza(session_factory, GcalConexion(profesional_id=mundo["bruno"], estado="activa"))


async def test_una_conexion_pendiente_exige_nonce_y_vencimiento(session_factory: Factory) -> None:
    from app.integraciones.gcal.models import GcalConexion

    mundo = await sembrar_mundo(session_factory)
    await _rechaza(session_factory, GcalConexion(profesional_id=mundo["bruno"], estado="pendiente"))


async def test_dos_eventos_vigentes_del_mismo_turno_y_conexion_se_rechazan(session_factory: Factory) -> None:
    _, conexion, turno = await _mundo(session_factory)
    await _rechaza(session_factory,
                   _evento(conexion, origen="sistema", turno_id=turno, google_event_id="evento-uno"),
                   _evento(conexion, origen="sistema", turno_id=turno, google_event_id="evento-dos"))


async def test_un_evento_borrado_mas_uno_vigente_del_mismo_turno_se_aceptan(session_factory: Factory) -> None:
    _, conexion, turno = await _mundo(session_factory)
    async with session_factory() as s:
        s.add_all([_evento(conexion, origen="sistema", turno_id=turno, google_event_id="evento-uno", estado="borrado"),
                   _evento(conexion, origen="sistema", turno_id=turno, google_event_id="evento-dos", generacion=1)])
        await s.flush()
        await s.rollback()


async def test_origen_google_con_turno_o_sistema_sin_turno_se_rechazan(session_factory: Factory) -> None:
    _, conexion, turno = await _mundo(session_factory)
    await _rechaza(session_factory, _evento(conexion, turno_id=turno))
    await _rechaza(session_factory, _evento(conexion, origen="sistema", turno_id=None))


async def test_el_mismo_id_de_google_en_la_misma_conexion_se_rechaza(session_factory: Factory) -> None:
    _, conexion, _ = await _mundo(session_factory)
    await _rechaza(session_factory, _evento(conexion), _evento(conexion))


@pytest.mark.parametrize("campos", [{"fin": INICIO}, {"fin": INICIO - timedelta(minutes=1)}, {"origen": "otro"},
                                    {"estado": "perdido"}, {"google_event_id": "abc"}, {"etag": "e" * 256}])
async def test_los_checks_de_evento_rechazan_valores_invalidos(session_factory: Factory,
                                                               campos: dict[str, Any]) -> None:
    _, conexion, _ = await _mundo(session_factory)
    await _rechaza(session_factory, _evento(conexion, **campos))


def _conflicto(conexion_id: int, turno_id: int, evento_id: int, **campos: Any) -> Any:
    from app.integraciones.gcal.models import GcalConflicto

    base: dict[str, Any] = {"conexion_id": conexion_id, "turno_id": turno_id, "evento_id": evento_id,
                            "tipo": "solapa_evento_externo", "sistema_inicio": INICIO,
                            "sistema_fin": INICIO + timedelta(minutes=30), "google_inicio": INICIO,
                            "google_fin": INICIO + timedelta(hours=1)}
    base.update(campos)
    return GcalConflicto(**base)


async def _con_franja(factory: Factory) -> tuple[int, int, int]:
    _, conexion, turno = await _mundo(factory)
    async with factory() as s:
        franja = _evento(conexion)
        s.add(franja)
        await s.flush()
        await s.commit()
        return conexion, turno, int(franja.id)


async def test_dos_conflictos_abiertos_del_mismo_tipo_y_par_se_rechazan(session_factory: Factory) -> None:
    conexion, turno, franja = await _con_franja(session_factory)
    await _rechaza(session_factory, _conflicto(conexion, turno, franja), _conflicto(conexion, turno, franja))


async def test_un_conflicto_resuelto_mas_uno_abierto_del_mismo_par_se_aceptan(session_factory: Factory) -> None:
    conexion, turno, franja = await _con_franja(session_factory)
    async with session_factory() as s:
        s.add_all([_conflicto(conexion, turno, franja, estado="resuelto", resolucion="revisado",
                              resuelto_en=INICIO), _conflicto(conexion, turno, franja)])
        await s.flush()
        await s.rollback()


@pytest.mark.parametrize("campos", [{"estado": "resuelto"}, {"resolucion": "revisado"}, {"tipo": "otro"},
                                    {"estado": "resuelto", "resolucion": "magia", "resuelto_en": INICIO}])
async def test_los_checks_de_conflicto_rechazan_estados_incoherentes(session_factory: Factory,
                                                                     campos: dict[str, Any]) -> None:
    conexion, turno, franja = await _con_franja(session_factory)
    await _rechaza(session_factory, _conflicto(conexion, turno, franja, **campos))


# --- 2.4 Reversibilidad ------------------------------------------------------------------------------------------

async def test_el_downgrade_borra_las_tablas_y_el_upgrade_las_recrea() -> None:
    abajo = alembic("downgrade", "010_recordatorios")
    try:
        assert abajo.returncode == 0, abajo.stderr
        assert "011_google_calendar" not in alembic("current").stdout
    finally:
        arriba = alembic("upgrade", "head")
    assert arriba.returncode == 0, arriba.stderr
