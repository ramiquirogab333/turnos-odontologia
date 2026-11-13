"""C-12 (1.1-1.5): migración 009_caja_cierres_devol contra PostgreSQL real. Datos sintéticos (R19).

Las invariantes se prueban con SQL de test (como las migraciones anteriores): los modelos ORM llegan en la tarea 1.6
y el trigger de inmutabilidad se vuelve a probar desde la aplicación en la 3.5.
"""

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.alembic_helpers import alembic

INICIO = datetime(2031, 5, 5, 13, 0, tzinfo=timezone.utc)
DIA = date(2031, 5, 5)
REEMBOLSO = datetime(2031, 5, 6, 15, 0, tzinfo=timezone.utc)


async def _turno(s: AsyncSession, ids: dict[str, int], inicio: datetime = INICIO) -> int:
    return int((await s.execute(text(
        "INSERT INTO turno (profesional_id, sillon_id, tratamiento_id, inicio, fin, estado) "
        "VALUES (:p, :s, :t, :i, :f, 'reservado') RETURNING id"),
        {"p": ids["profesional_id"], "s": ids["sillon_id"], "t": ids["tratamiento_id"],
         "i": inicio, "f": inicio + timedelta(minutes=30)})).scalar_one())


async def _pago(s: AsyncSession, turno_id: int, *, estado: str = "a_reembolsar", referencia: str = "ref-sint-0001",
                acreditado_en: datetime | None = INICIO, reembolsado_en: datetime | None = None,
                reembolso_referencia: str | None = None) -> int:
    return int((await s.execute(text(
        "INSERT INTO pago_sena (turno_id, medio, monto, porcentaje_aplicado, estado, referencia_externa, vence_en, "
        "acreditado_en, reembolsado_en, reembolso_referencia) "
        "VALUES (:t, 'transferencia', 300.00, 30.00, :e, :r, :v, :a, :re, :rr) RETURNING id"),
        {"t": turno_id, "e": estado, "r": referencia, "v": INICIO, "a": acreditado_en, "re": reembolsado_en,
         "rr": reembolso_referencia})).scalar_one())


async def _cierre(s: AsyncSession, *, dia: date = DIA, estado: str = "vigente", ingresos: str = "1500.00",
                  egresos: str = "0.00", neto: str = "1500.00") -> int:
    anulado = ", anulado_en, anulado_motivo" if estado == "anulado" else ""
    valores = ", now(), 'error de carga sintetico'" if estado == "anulado" else ""
    return int((await s.execute(text(
        f"INSERT INTO cierre_caja (dia, estado, total_ingresos, total_egresos, total_neto{anulado}) "
        f"VALUES (:d, :e, :i, :g, :n{valores}) RETURNING id"),
        {"d": dia, "e": estado, "i": ingresos, "g": egresos, "n": neto})).scalar_one())


async def _linea(s: AsyncSession, cierre_id: int, concepto: str = "sena", medio: str = "mercadopago",
                 total: str = "1500.00") -> int:
    return int((await s.execute(text(
        "INSERT INTO cierre_caja_linea (cierre_id, concepto, medio, cantidad, total) "
        "VALUES (:c, :co, :m, 1, :t) RETURNING id"),
        {"c": cierre_id, "co": concepto, "m": medio, "t": total})).scalar_one())


# --- 1.1 Esquema -------------------------------------------------------------------------------------------------

async def test_existen_las_tablas_nuevas_con_tipos_de_dinero_fecha_y_dia_correctos(
        session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as s:
        tipos = {(t, c): d for t, c, d in (await s.execute(text(
            "SELECT table_name, column_name, data_type FROM information_schema.columns "
            "WHERE table_name IN ('cierre_caja', 'cierre_caja_linea', 'pago_sena', 'pago_sena_aprobacion')"))).all()}
    assert tipos[("cierre_caja", "dia")] == "date"
    for col in ("total_ingresos", "total_egresos", "total_neto"):
        assert tipos[("cierre_caja", col)] == "numeric"
    for col in ("cerrado_en", "anulado_en"):
        assert tipos[("cierre_caja", col)] == "timestamp with time zone"
    assert tipos[("cierre_caja_linea", "total")] == "numeric"
    assert tipos[("pago_sena", "reembolsado_en")] == "timestamp with time zone"
    assert tipos[("pago_sena_aprobacion", "reembolsado_en")] == "timestamp with time zone"
    assert tipos[("pago_sena", "reembolso_referencia")] == "text"


async def test_cada_fk_de_las_tablas_tocadas_tiene_un_indice_que_empieza_por_su_columna(
        session_factory: async_sessionmaker[AsyncSession]) -> None:
    """R6: PostgreSQL no indexa las FK solo."""
    async with session_factory() as s:
        fks = {(t, c) for t, c in (await s.execute(text(
            "SELECT c.conrelid::regclass::text, a.attname FROM pg_constraint c "
            "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1] "
            "WHERE c.contype = 'f' AND c.conrelid = ANY(ARRAY['cierre_caja'::regclass, "
            "'cierre_caja_linea'::regclass, 'pago_sena'::regclass, 'pago_sena_aprobacion'::regclass])"))).all()}
        sin_indice = {(t, c) for t, c in (await s.execute(text(
            "SELECT c.conrelid::regclass::text, a.attname FROM pg_constraint c "
            "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1] "
            "WHERE c.contype = 'f' AND c.conrelid = ANY(ARRAY['cierre_caja'::regclass, "
            "'cierre_caja_linea'::regclass, 'pago_sena'::regclass, 'pago_sena_aprobacion'::regclass]) "
            "AND NOT EXISTS (SELECT 1 FROM pg_index i WHERE i.indrelid = c.conrelid "
            "AND i.indkey[0] = c.conkey[1])"))).all()}
    esperadas = {("cierre_caja", "cerrado_por"), ("cierre_caja", "anulado_por"), ("cierre_caja_linea", "cierre_id"),
                 ("pago_sena", "reembolsado_por_usuario_id"), ("pago_sena_aprobacion", "reembolsado_por_usuario_id"),
                 ("pago_sena", "turno_id"), ("pago_sena", "acreditado_por_usuario_id"),
                 ("pago_sena_aprobacion", "pago_id")}
    assert esperadas <= fks
    assert sin_indice == set()


async def test_la_extension_unaccent_esta_instalada(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as s:
        assert (await s.execute(text("SELECT unaccent('Lucía')"))).scalar_one() == "Lucia"


# --- 1.2 Invariantes ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("tabla", ["pago_sena", "pago_sena_aprobacion"])
async def test_el_estado_reembolsado_se_acepta_en_las_dos_tablas_de_pagos(
        session_factory: async_sessionmaker[AsyncSession], seed_ids: dict[str, int], tabla: str) -> None:
    async with session_factory() as s:
        turno = await _turno(s, seed_ids)
        if tabla == "pago_sena":
            await _pago(s, turno, estado="reembolsado", reembolsado_en=REEMBOLSO, reembolso_referencia="DEV-SINT-0001")
        else:
            pago = await _pago(s, turno, estado="a_reembolsar")
            await s.execute(text(
                "INSERT INTO pago_sena_aprobacion (pago_id, mp_payment_id, estado, reembolsado_en, "
                "reembolso_referencia) VALUES (:p, 'mp-sint-1', 'reembolsado', :f, 'DEV-SINT-0002')"),
                {"p": pago, "f": REEMBOLSO})
        await s.rollback()


@pytest.mark.parametrize("campos", [
    {"reembolsado_en": None, "reembolso_referencia": "DEV-SINT-0001"},
    {"reembolsado_en": REEMBOLSO, "reembolso_referencia": None},
    {"reembolsado_en": REEMBOLSO, "reembolso_referencia": "ab"},
    {"reembolsado_en": REEMBOLSO, "reembolso_referencia": "x" * 65},
])
async def test_reembolsado_sin_fecha_o_sin_referencia_valida_se_rechaza(
        session_factory: async_sessionmaker[AsyncSession], seed_ids: dict[str, int],
        campos: dict[str, object]) -> None:
    async with session_factory() as s:
        turno = await _turno(s, seed_ids)
        with pytest.raises(IntegrityError):
            await _pago(s, turno, estado="reembolsado", **campos)  # type: ignore[arg-type]
        await s.rollback()


async def test_un_pago_que_no_esta_reembolsado_no_puede_tener_datos_de_devolucion(
        session_factory: async_sessionmaker[AsyncSession], seed_ids: dict[str, int]) -> None:
    async with session_factory() as s:
        turno = await _turno(s, seed_ids)
        with pytest.raises(IntegrityError):
            await _pago(s, turno, estado="a_reembolsar", reembolsado_en=REEMBOLSO,
                        reembolso_referencia="DEV-SINT-0001")
        await s.rollback()


async def test_dos_cierres_vigentes_del_mismo_dia_se_rechazan_y_uno_anulado_mas_uno_vigente_se_aceptan(
        session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as s:
        await _cierre(s, estado="vigente")
        with pytest.raises(IntegrityError):
            async with s.begin_nested():
                await _cierre(s, estado="vigente")
        await _cierre(s, estado="vigente", dia=DIA + timedelta(days=1))  # otro día: libre
        await s.rollback()
    async with session_factory() as s:
        await _cierre(s, estado="anulado")
        await _cierre(s, estado="vigente")
        await _cierre(s, estado="anulado")  # varios anulados del mismo día conviven
        await s.rollback()


async def test_el_total_neto_distinto_de_la_resta_se_rechaza(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as s:
        await _cierre(s, ingresos="3000.00", egresos="500.00", neto="2500.00")  # coherente
        with pytest.raises(IntegrityError):
            async with s.begin_nested():
                await _cierre(s, dia=DIA + timedelta(days=1), ingresos="3000.00", egresos="500.00", neto="2999.99")
        with pytest.raises(IntegrityError):
            async with s.begin_nested():
                await _cierre(s, dia=DIA + timedelta(days=2), ingresos="-1.00", egresos="0.00", neto="-1.00")
        await s.rollback()


@pytest.mark.parametrize("concepto,medio", [("efectivo", "mercadopago"), ("sena", "efectivo"),
                                            ("devolucion_sena", "tarjeta")])
async def test_una_linea_con_concepto_o_medio_fuera_del_catalogo_se_rechaza(
        session_factory: async_sessionmaker[AsyncSession], concepto: str, medio: str) -> None:
    async with session_factory() as s:
        cierre = await _cierre(s)
        await _linea(s, cierre, "pago_presupuesto", "transferencia")  # válida
        with pytest.raises(IntegrityError):
            async with s.begin_nested():
                await _linea(s, cierre, concepto, medio)
        await s.rollback()


async def test_una_linea_por_concepto_y_medio_en_cada_cierre(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as s:
        cierre = await _cierre(s)
        await _linea(s, cierre)
        with pytest.raises(IntegrityError):
            async with s.begin_nested():
                await _linea(s, cierre)
        await s.rollback()


async def test_la_anulacion_exige_fecha_y_motivo_de_3_a_300_caracteres(
        session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as s:
        for motivo in ("ab", "x" * 301):
            with pytest.raises(IntegrityError):
                async with s.begin_nested():
                    await s.execute(text(
                        "INSERT INTO cierre_caja (dia, estado, total_ingresos, total_egresos, total_neto, "
                        "anulado_en, anulado_motivo) VALUES (:d, 'anulado', 0, 0, 0, now(), :m)"),
                        {"d": DIA, "m": motivo})
        with pytest.raises(IntegrityError):  # un vigente no trae datos de anulación
            async with s.begin_nested():
                await s.execute(text(
                    "INSERT INTO cierre_caja (dia, estado, total_ingresos, total_egresos, total_neto, anulado_motivo) "
                    "VALUES (:d, 'vigente', 0, 0, 0, 'motivo sintetico')"), {"d": DIA})
        await s.rollback()


# --- 1.3 Trigger de inmutabilidad --------------------------------------------------------------------------------

@pytest.mark.parametrize("sentencia", [
    "UPDATE cierre_caja_linea SET total = 1.00 WHERE id = :l",
    "UPDATE cierre_caja_linea SET cantidad = 9 WHERE id = :l",
    "UPDATE cierre_caja SET total_neto = 1.00, total_ingresos = 1.00 WHERE id = :c",
    "UPDATE cierre_caja SET dia = dia + 1 WHERE id = :c",
    "UPDATE cierre_caja SET observaciones = 'cambio' WHERE id = :c",
])
async def test_el_trigger_rechaza_cambiar_importes_o_dia_de_un_cierre_y_sus_lineas(
        session_factory: async_sessionmaker[AsyncSession], sentencia: str) -> None:
    async with session_factory() as s:
        cierre = await _cierre(s)
        linea = await _linea(s, cierre)
        with pytest.raises(DBAPIError):
            await s.execute(text(sentencia), {"c": cierre, "l": linea})
        await s.rollback()


async def test_el_trigger_acepta_pasar_de_vigente_a_anulado_con_sus_tres_campos_y_no_deja_volver(
        session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as s:
        cierre = await _cierre(s)
        await s.execute(text(
            "UPDATE cierre_caja SET estado = 'anulado', anulado_en = now(), anulado_motivo = 'error de carga sintetico' "
            "WHERE id = :c"), {"c": cierre})
        assert (await s.execute(text("SELECT estado FROM cierre_caja WHERE id = :c"), {"c": cierre})).scalar_one() \
            == "anulado"
        with pytest.raises(DBAPIError):  # anulado -> vigente
            async with s.begin_nested():
                await s.execute(text(
                    "UPDATE cierre_caja SET estado = 'vigente', anulado_en = NULL, anulado_motivo = NULL "
                    "WHERE id = :c"), {"c": cierre})
        with pytest.raises(DBAPIError):  # un anulado no cambia el motivo
            async with s.begin_nested():
                await s.execute(text("UPDATE cierre_caja SET anulado_motivo = 'otro motivo' WHERE id = :c"),
                                {"c": cierre})
        await s.rollback()


async def test_borrar_un_usuario_no_se_bloquea_por_el_trigger_del_cierre(
        session_factory: async_sessionmaker[AsyncSession]) -> None:
    """La FK ``SET NULL`` actualiza el cierre: el trigger deja pasar ese cambio y solo ese."""
    async with session_factory() as s:
        usuario = (await s.execute(text(
            "INSERT INTO usuario (email, nombre_completo, hashed_password) "
            "VALUES ('cierre@turnos.test', 'Usuario Sintetico', 'x') RETURNING id"))).scalar_one()
        cierre = int((await s.execute(text(
            "INSERT INTO cierre_caja (dia, total_ingresos, total_egresos, total_neto, cerrado_por) "
            "VALUES (:d, 0, 0, 0, :u) RETURNING id"), {"d": DIA, "u": usuario})).scalar_one())
        await s.execute(text("DELETE FROM usuario WHERE id = :u"), {"u": usuario})
        assert (await s.execute(text("SELECT cerrado_por FROM cierre_caja WHERE id = :c"),
                                {"c": cierre})).scalar_one() is None
        with pytest.raises(DBAPIError):  # cambiar quién cerró a otro usuario sí está prohibido
            async with s.begin_nested():
                otro = (await s.execute(text(
                    "INSERT INTO usuario (email, nombre_completo, hashed_password) "
                    "VALUES ('cierre2@turnos.test', 'Usuario Sintetico', 'x') RETURNING id"))).scalar_one()
                await s.execute(text("UPDATE cierre_caja SET cerrado_por = :u WHERE id = :c"),
                                {"u": otro, "c": cierre})
        await s.rollback()


# --- 1.5 Relleno y reversibilidad --------------------------------------------------------------------------------

async def test_upgrade_rellena_acreditado_en_y_downgrade_devuelve_los_reembolsados_y_quita_todo(
        session_factory: async_sessionmaker[AsyncSession], seed_ids: dict[str, int]) -> None:
    try:
        abajo = alembic("downgrade", "008_ficha_odonto_presup")
        assert abajo.returncode == 0, abajo.stderr
        async with session_factory() as s:
            tablas = set((await s.execute(text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' "
                "AND table_name IN ('cierre_caja', 'cierre_caja_linea')"))).scalars().all())
            columnas = (await s.execute(text(
                "SELECT count(*) FROM information_schema.columns WHERE table_name IN ('pago_sena', "
                "'pago_sena_aprobacion') AND column_name LIKE 'reembols%'"))).scalar_one()
            extension = (await s.execute(text(
                "SELECT count(*) FROM pg_extension WHERE extname = 'unaccent'"))).scalar_one()
            assert (tablas, columnas, extension) == (set(), 0, 0)
            turno = await _turno(s, seed_ids)
            await s.execute(text(
                "INSERT INTO pago_sena (turno_id, medio, monto, porcentaje_aplicado, estado, referencia_externa, "
                "vence_en, updated_at) VALUES (:t, 'transferencia', 300.00, 30.00, 'a_reembolsar', 'ref-sint-0009', "
                ":v, :u)"), {"t": turno, "v": INICIO, "u": REEMBOLSO})
            await s.commit()
        arriba = alembic("upgrade", "head")
        assert arriba.returncode == 0, arriba.stderr
        async with session_factory() as s:
            acreditado_en = (await s.execute(text(
                "SELECT acreditado_en FROM pago_sena WHERE referencia_externa = 'ref-sint-0009'"))).scalar_one()
            assert acreditado_en == REEMBOLSO  # = updated_at
            await s.execute(text(
                "UPDATE pago_sena SET estado = 'reembolsado', reembolsado_en = :f, reembolso_referencia = 'DEV-SINT-1' "
                "WHERE referencia_externa = 'ref-sint-0009'"), {"f": REEMBOLSO})
            await s.commit()
        abajo = alembic("downgrade", "008_ficha_odonto_presup")
        assert abajo.returncode == 0, abajo.stderr
        async with session_factory() as s:
            assert (await s.execute(text(
                "SELECT estado FROM pago_sena WHERE referencia_externa = 'ref-sint-0009'"))).scalar_one() \
                == "a_reembolsar"
            assert (await s.execute(text(
                "SELECT count(*) FROM pg_trigger WHERE tgname LIKE 'trg_cierre_caja%'"))).scalar_one() == 0
    finally:
        arriba = alembic("upgrade", "head")
        assert arriba.returncode == 0, arriba.stderr
        async with session_factory() as s:
            await s.execute(text("DELETE FROM pago_sena"))
            await s.execute(text("DELETE FROM turno"))
            await s.commit()
    async with session_factory() as s:
        assert (await s.execute(text("SELECT count(*) FROM cierre_caja"))).scalar_one() == 0
        assert (await s.execute(text("SELECT version_num FROM alembic_version"))).scalar_one() \
            == "011_google_calendar"


# --- 1.6 Modelos -------------------------------------------------------------------------------------------------

def test_los_modelos_nuevos_declaran_indices_de_fk_y_tipos_de_dinero_y_fecha() -> None:
    from sqlalchemy import DateTime, Numeric

    from app.caja.models import CierreCaja, CierreCajaLinea
    from app.pagos.models import AprobacionPago, PagoSena

    for modelo, fks in ((CierreCaja, {"cerrado_por", "anulado_por"}),
                        (PagoSena, {"reembolsado_por_usuario_id"}),
                        (AprobacionPago, {"reembolsado_por_usuario_id"})):
        indexadas = {c.name for i in modelo.__table__.indexes for c in i.columns}
        assert fks <= indexadas, modelo.__name__
    unica = [set(c.name for c in k.columns) for k in CierreCajaLinea.__table__.constraints
             if k.__class__.__name__ == "UniqueConstraint"]
    assert {"cierre_id", "concepto", "medio"} in unica  # el prefijo cierre_id cubre la FK
    for col in ("total_ingresos", "total_egresos", "total_neto"):
        tipo = CierreCaja.__table__.c[col].type
        assert isinstance(tipo, Numeric) and tipo.scale == 2
    for col in ("cerrado_en", "anulado_en"):
        tipo = CierreCaja.__table__.c[col].type
        assert isinstance(tipo, DateTime) and tipo.timezone is True


def test_el_catalogo_de_estados_del_pago_incluye_reembolsado_como_ultimo_estado() -> None:
    from app.pagos.models import ESTADOS_PAGO, PagoSena

    assert ESTADOS_PAGO[-1] == "reembolsado" and len(set(ESTADOS_PAGO)) == 7
    checks = [str(k.sqltext) for k in PagoSena.__table__.constraints if k.__class__.__name__ == "CheckConstraint"]
    assert any("estado IN" in c and "reembolsado" in c for c in checks)
