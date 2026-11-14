"""C-14 (1.1, 1.3; D3, D5, D6; O1, O6, O13): migración 014 — baja lógica del catálogo y restricciones en la base.

Datos 100 % sintéticos (R19). Los tests de ``downgrade`` devuelven la base a ``head`` en un ``finally``.
"""

import asyncio
from datetime import time

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.alembic_helpers import alembic

Factory = async_sessionmaker[AsyncSession]
HEAD = "014_catalogo_baja_logica"
ANTERIOR = "013_auditoria_exportacion"


async def _profesional(s: AsyncSession, nombre: str = "Dra. Ana Ficticia", matricula: str = "MP-99001") -> int:
    return int((await s.execute(text(
        "INSERT INTO profesional (nombre, matricula, especialidad) VALUES (:n, :m, '') RETURNING id"),
        {"n": nombre, "m": matricula})).scalar_one())


async def _franja(s: AsyncSession, profesional: int, inicio: str, fin: str, dia: int = 0, activa: bool = True) -> int:
    return int((await s.execute(text(
        "INSERT INTO disponibilidad (profesional_id, dia_semana, hora_inicio, hora_fin, is_active) "
        "VALUES (:p, :d, :i, :f, :a) RETURNING id"),
        {"p": profesional, "d": dia, "i": time.fromisoformat(inicio), "f": time.fromisoformat(fin), "a": activa}
    )).scalar_one())


def _sqlstate(exc: IntegrityError) -> str | None:
    return getattr(exc.orig, "sqlstate", None)


# --- Esquema tras `upgrade head` -------------------------------------------------------------------------------------

async def test_las_filas_previas_de_tratamiento_y_profesional_quedan_activas_y_la_columna_es_not_null_default_true(
        session_factory: Factory) -> None:
    async with session_factory() as s:
        columnas = (await s.execute(text(
            "SELECT table_name, is_nullable, column_default FROM information_schema.columns "
            "WHERE column_name = 'is_active' AND table_name IN ('tratamiento', 'profesional') ORDER BY table_name"
        ))).all()
        assert [(c[0], c[1], c[2]) for c in columnas] == [("profesional", "NO", "true"), ("tratamiento", "NO", "true")]
        # Una fila insertada sin indicar `is_active` nace activa (la misma regla que aplica a las filas previas).
        await s.execute(text("INSERT INTO tratamiento (nombre, duracion_minutos, precio_base) VALUES ('Limpieza', 30, 1000)"))
        assert (await s.execute(text("SELECT is_active FROM tratamiento WHERE nombre = 'Limpieza'"))).scalar_one() is True
        await _profesional(s)
        assert (await s.execute(text("SELECT is_active FROM profesional"))).scalar_one() is True
        await s.rollback()


async def test_dos_franjas_activas_superpuestas_del_mismo_profesional_y_dia_fallan_con_23p01(session_factory: Factory) -> None:
    async with session_factory() as s:
        p = await _profesional(s)
        await _franja(s, p, "09:00", "13:00")
        with pytest.raises(IntegrityError) as exc:
            await _franja(s, p, "12:00", "15:00")
        assert _sqlstate(exc.value) == "23P01"
        await s.rollback()


async def test_franjas_contiguas_otro_dia_u_otro_profesional_se_aceptan(session_factory: Factory) -> None:
    async with session_factory() as s:
        ana = await _profesional(s)
        juan = await _profesional(s, "Dr. Juan Ejemplo", "MP-99002")
        await _franja(s, ana, "09:00", "13:00")
        await _franja(s, ana, "13:00", "17:00")  # contigua: el rango es semiabierto [)
        await _franja(s, ana, "09:00", "13:00", dia=1)  # otro día
        await _franja(s, juan, "09:00", "13:00")  # otro profesional
        assert (await s.execute(text("SELECT count(*) FROM disponibilidad"))).scalar_one() == 4
        await s.rollback()


async def test_una_franja_superpuesta_pero_inactiva_se_acepta_y_reactivarla_falla(session_factory: Factory) -> None:
    async with session_factory() as s:
        p = await _profesional(s)
        await _franja(s, p, "09:00", "13:00")
        pausada = await _franja(s, p, "12:00", "15:00", activa=False)
        with pytest.raises(IntegrityError) as exc:
            await s.execute(text("UPDATE disponibilidad SET is_active = true WHERE id = :i"), {"i": pausada})
        assert _sqlstate(exc.value) == "23P01"
        await s.rollback()


async def test_un_nombre_de_tratamiento_repetido_sin_distinguir_mayusculas_ni_espacios_falla_con_23505(
        session_factory: Factory) -> None:
    async with session_factory() as s:
        await s.execute(text("INSERT INTO tratamiento (nombre, duracion_minutos, precio_base) VALUES ('Limpieza dental', 30, 1000)"))
        with pytest.raises(IntegrityError) as exc:
            await s.execute(text(
                "INSERT INTO tratamiento (nombre, duracion_minutos, precio_base) VALUES (' limpieza DENTAL ', 30, 1000)"))
        assert _sqlstate(exc.value) == "23505"
        await s.rollback()


async def test_un_nombre_de_sillon_repetido_y_una_matricula_repetida_fallan_con_23505_y_los_distintos_se_aceptan(
        session_factory: Factory) -> None:
    async with session_factory() as s:
        await s.execute(text("INSERT INTO sillon (nombre, estado) VALUES ('Sillón 1', 'activo')"))
        await s.execute(text("INSERT INTO sillon (nombre, estado) VALUES ('Sillón 2', 'activo')"))
        with pytest.raises(IntegrityError) as exc:
            await s.execute(text("INSERT INTO sillon (nombre, estado) VALUES ('SILLÓN 1 ', 'inactivo')"))
        assert _sqlstate(exc.value) == "23505"
        await s.rollback()
    async with session_factory() as s:
        await _profesional(s, matricula="MP-99001")
        await _profesional(s, "Dr. Juan Ejemplo", "MP-99002")
        with pytest.raises(IntegrityError) as exc:
            await _profesional(s, "Otro Ejemplo", "mp-99001")
        assert _sqlstate(exc.value) == "23505"
        await s.rollback()


# --- 1.3 Datos existentes y reversibilidad -----------------------------------------------------------------------------

async def _version(factory: Factory) -> str:
    async with factory() as s:
        return str((await s.execute(text("SELECT version_num FROM alembic_version"))).scalar_one())


async def test_con_franjas_superpuestas_en_013_el_upgrade_se_detiene_nombrando_ambos_ids_y_la_base_queda_en_013(
        session_factory: Factory) -> None:
    abajo = alembic("downgrade", "-1")
    assert abajo.returncode == 0, abajo.stderr
    try:
        async with session_factory() as s:
            p = await _profesional(s)
            a = await _franja(s, p, "09:00", "13:00")
            b = await _franja(s, p, "12:00", "15:00")
            await s.commit()
        arriba = alembic("upgrade", "head")
        assert arriba.returncode != 0
        assert f"{a}" in arriba.stderr and f"{b}" in arriba.stderr
        assert "franjas" in arriba.stderr.lower()
        assert await _version(session_factory) == ANTERIOR
        async with session_factory() as s:  # no se corrigió nada solo
            assert (await s.execute(text("SELECT count(*) FROM disponibilidad"))).scalar_one() == 2
    finally:
        async with session_factory() as s:
            await s.execute(text("DELETE FROM disponibilidad"))
            await s.execute(text("DELETE FROM profesional"))
            await s.commit()
        arriba = alembic("upgrade", "head")
        assert arriba.returncode == 0, arriba.stderr
    assert await _version(session_factory) == HEAD


@pytest.mark.parametrize(
    ("tabla", "insercion", "aviso"),
    [
        ("tratamiento", "INSERT INTO tratamiento (nombre, duracion_minutos, precio_base) VALUES ('Limpieza', 30, 1000), (' limpieza ', 30, 1000)", "tratamiento"),
        ("sillon", "INSERT INTO sillon (nombre, estado) VALUES ('Sillón 1', 'activo'), ('sillón 1', 'activo')", "sill"),
        ("profesional", "INSERT INTO profesional (nombre, matricula) VALUES ('Dra. Ana Ficticia', 'MP-99001'), ('Dr. Juan Ejemplo', 'mp-99001')", "matr"),
    ],
)
async def test_con_nombres_o_matriculas_duplicados_en_013_el_upgrade_se_detiene_y_nombra_los_ids(
        session_factory: Factory, tabla: str, insercion: str, aviso: str) -> None:
    abajo = alembic("downgrade", "-1")
    assert abajo.returncode == 0, abajo.stderr
    try:
        async with session_factory() as s:
            await s.execute(text(insercion))
            ids = [int(i) for i in (await s.execute(text(f"SELECT id FROM {tabla} ORDER BY id"))).scalars().all()]
            await s.commit()
        arriba = alembic("upgrade", "head")
        assert arriba.returncode != 0
        assert aviso in arriba.stderr.lower()
        assert all(str(i) in arriba.stderr for i in ids)
        assert await _version(session_factory) == ANTERIOR
    finally:
        async with session_factory() as s:
            await s.execute(text(f"DELETE FROM {tabla}"))
            await s.commit()
        arriba = alembic("upgrade", "head")
        assert arriba.returncode == 0, arriba.stderr


async def test_el_downgrade_quita_columnas_restricciones_y_tipo_sin_perder_filas_y_el_upgrade_los_restituye(
        session_factory: Factory) -> None:
    async with session_factory() as s:
        p = await _profesional(s)
        await _franja(s, p, "09:00", "13:00")
        await s.execute(text("INSERT INTO tratamiento (nombre, duracion_minutos, precio_base) VALUES ('Limpieza', 30, 1000)"))
        await s.commit()
    abajo = alembic("downgrade", "-1")
    try:
        assert abajo.returncode == 0, abajo.stderr
        async with session_factory() as s:
            columnas = (await s.execute(text(
                "SELECT count(*) FROM information_schema.columns WHERE column_name = 'is_active' "
                "AND table_name IN ('tratamiento', 'profesional')"))).scalar_one()
            restricciones = (await s.execute(text(
                "SELECT count(*) FROM pg_constraint WHERE conname = 'ex_disponibilidad_franja_activa'"))).scalar_one()
            indices = (await s.execute(text(
                "SELECT count(*) FROM pg_indexes WHERE indexname IN "
                "('ux_tratamiento_nombre', 'ux_sillon_nombre', 'ux_profesional_matricula')"))).scalar_one()
            tipo = (await s.execute(text("SELECT count(*) FROM pg_type WHERE typname = 'rango_hora'"))).scalar_one()
            filas = [(await s.execute(text(f"SELECT count(*) FROM {t}"))).scalar_one()
                     for t in ("profesional", "disponibilidad", "tratamiento")]
        assert (columnas, restricciones, indices, tipo) == (0, 0, 0, 0)
        assert filas == [1, 1, 1]
        assert await _version(session_factory) == ANTERIOR
    finally:
        arriba = alembic("upgrade", "head")
        assert arriba.returncode == 0, arriba.stderr
    assert await _version(session_factory) == HEAD
    async with session_factory() as s:  # las filas siguen y quedan activas
        assert (await s.execute(text("SELECT is_active FROM tratamiento"))).scalar_one() is True
        assert (await s.execute(text("SELECT is_active FROM profesional"))).scalar_one() is True


async def test_dos_altas_de_franjas_superpuestas_al_mismo_tiempo_dejan_una_sola_en_la_base(session_factory: Factory) -> None:
    async with session_factory() as s:
        p = await _profesional(s)
        await s.commit()

    async def alta(inicio: str, fin: str) -> str:
        async with session_factory() as s:
            try:
                await _franja(s, p, inicio, fin)
                await s.commit()
                return "ok"
            except IntegrityError as exc:
                await s.rollback()
                return str(_sqlstate(exc))

    resultados = await asyncio.gather(alta("10:00", "12:00"), alta("11:00", "14:00"))
    assert sorted(resultados) == ["23P01", "ok"]
