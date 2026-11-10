"""C-11 (grupo 1): migración 008 contra PostgreSQL real. Datos 100 % sintéticos (R19)."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.alembic_helpers import alembic

TABLAS = ("ficha", "odontograma_registro", "presupuesto", "presupuesto_linea", "pago_presupuesto")
AHORA = datetime(2031, 5, 5, 15, 0, tzinfo=timezone.utc)


async def test_existen_las_cinco_tablas(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as s:
        filas = (await s.execute(text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' "
            "AND table_name = ANY(:t)"), {"t": list(TABLAS)})).scalars().all()
    assert sorted(filas) == sorted(TABLAS)


async def test_cada_fk_tiene_un_indice_con_esa_columna_como_prefijo(
        session_factory: async_sessionmaker[AsyncSession]) -> None:
    """R6: PostgreSQL no indexa las FK. Se compara cada FK con la primera columna de algún índice de la tabla."""
    async with session_factory() as s:
        fks = (await s.execute(text(
            "SELECT c.conrelid::regclass::text AS tabla, a.attname AS columna, c.conrelid AS oid, a.attnum AS num "
            "FROM pg_constraint c JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1] "
            "WHERE c.contype = 'f' AND c.conrelid::regclass::text = ANY(:t)"), {"t": list(TABLAS)})).all()
        assert len(fks) >= 12  # ficha 2, odontograma 2, presupuesto 3, línea 3, pago 3 o más
        sin_indice = []
        for fk in fks:
            prefijo = (await s.execute(text(
                "SELECT count(*) FROM pg_index i WHERE i.indrelid = :oid AND i.indkey[0] = :num"),
                {"oid": fk.oid, "num": fk.num})).scalar_one()
            if prefijo == 0:
                sin_indice.append(f"{fk.tabla}.{fk.columna}")
    assert sin_indice == []


async def test_ficha_actualizado_por_y_registrado_por_estan_indexadas(
        session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as s:
        for tabla, columna in (("ficha", "actualizado_por"), ("odontograma_registro", "registrado_por")):
            n = (await s.execute(text(
                "SELECT count(*) FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid "
                "AND a.attnum = i.indkey[0] WHERE i.indrelid = CAST(:t AS regclass) AND a.attname = :c"),
                {"t": tabla, "c": columna})).scalar_one()
            assert n >= 1, f"{tabla}.{columna} sin índice"


async def test_montos_son_numeric_y_fechas_timestamptz(session_factory: async_sessionmaker[AsyncSession]) -> None:
    montos = [("presupuesto", c) for c in ("subtotal", "cobertura_total", "diferencial_total", "total_paciente")]
    montos += [("presupuesto_linea", c) for c in ("precio_unitario", "importe_bruto", "importe_cobertura",
                                                  "importe_diferencial", "importe_paciente")]
    montos += [("pago_presupuesto", "monto")]
    fechas = [("ficha", "created_at"), ("odontograma_registro", "registrado_en"), ("presupuesto", "presentado_en"),
              ("presupuesto", "anulado_en"), ("pago_presupuesto", "fecha_cobro"), ("pago_presupuesto", "anulado_en")]
    async with session_factory() as s:
        for tabla, columna in montos:
            tipo = (await s.execute(text(
                "SELECT data_type FROM information_schema.columns WHERE table_name = :t AND column_name = :c"),
                {"t": tabla, "c": columna})).scalar_one()
            assert tipo == "numeric", f"{tabla}.{columna} es {tipo}"
        for tabla, columna in fechas:
            tipo = (await s.execute(text(
                "SELECT data_type FROM information_schema.columns WHERE table_name = :t AND column_name = :c"),
                {"t": tabla, "c": columna})).scalar_one()
            assert tipo == "timestamp with time zone", f"{tabla}.{columna} es {tipo}"


# --- 1.3 TRIANGULAR: la base rechaza lo inválido con INSERT directos -----------------------------------------

async def _paciente(s: AsyncSession, dni: str = "99000001") -> int:
    return int((await s.execute(text(
        "INSERT INTO paciente (nombre, apellido, dni, telefono, is_active) "
        "VALUES ('Lucía', 'Ejemplo', :d, '+5491100000001', true) RETURNING id"), {"d": dni})).scalar_one())


async def _presupuesto(s: AsyncSession, paciente_id: int, *, subtotal: str = "100.00", cobertura: str = "90.00",
                       diferencial: str = "0.00", total: str = "10.00") -> int:
    return int((await s.execute(text(
        "INSERT INTO presupuesto (paciente_id, estado, subtotal, cobertura_total, diferencial_total, total_paciente) "
        "VALUES (:p, 'borrador', :s, :c, :d, :t) RETURNING id"),
        {"p": paciente_id, "s": Decimal(subtotal), "c": Decimal(cobertura), "d": Decimal(diferencial),
         "t": Decimal(total)})).scalar_one())


@pytest.mark.parametrize("pieza,cara,estado", [
    (19, None, "ausente"), (56, None, "ausente"), (16, "X", "caries"), (16, None, "caries"),
    (16, "O", "corona"), (16, "O", "inexistente"), (86, None, "ausente"), (10, None, "ausente")])
async def test_odontograma_rechaza_registros_invalidos(session_factory: async_sessionmaker[AsyncSession],
                                                       pieza: int, cara: str | None, estado: str) -> None:
    async with session_factory() as s:
        paciente_id = await _paciente(s)
        with pytest.raises(IntegrityError):
            await s.execute(text(
                "INSERT INTO odontograma_registro (paciente_id, pieza, cara, estado) VALUES (:p, :pi, :c, :e)"),
                {"p": paciente_id, "pi": pieza, "c": cara, "e": estado})
        await s.rollback()


@pytest.mark.parametrize("pieza,cara,estado", [
    (18, "O", "caries"), (55, None, "extraccion_indicada"), (85, "L", "obturado"), (26, None, "sano"),
    (26, "M", "sano"), (11, None, "implante")])
async def test_odontograma_acepta_registros_validos(session_factory: async_sessionmaker[AsyncSession],
                                                    pieza: int, cara: str | None, estado: str) -> None:
    async with session_factory() as s:
        paciente_id = await _paciente(s)
        await s.execute(text(
            "INSERT INTO odontograma_registro (paciente_id, pieza, cara, estado) VALUES (:p, :pi, :c, :e)"),
            {"p": paciente_id, "pi": pieza, "c": cara, "e": estado})
        await s.rollback()


async def test_presupuesto_rechaza_total_que_no_cumple_la_formula(
        session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as s:
        paciente_id = await _paciente(s)
        with pytest.raises(IntegrityError):
            await _presupuesto(s, paciente_id, total="11.00")
        await s.rollback()
        paciente_id = await _paciente(s)
        # total = subtotal - cobertura + diferencial: 100 - 90 + 5 = 15 se acepta
        await _presupuesto(s, paciente_id, diferencial="5.00", total="15.00")
        await s.rollback()


async def test_linea_rechaza_cobertura_mayor_al_bruto_y_formula_inconsistente(
        session_factory: async_sessionmaker[AsyncSession], seed_ids: dict[str, int]) -> None:
    sql = ("INSERT INTO presupuesto_linea (presupuesto_id, orden, tratamiento_id, cantidad, precio_unitario, "
           "cobertura_porcentaje, arancel_diferencial, importe_bruto, importe_cobertura, importe_diferencial, "
           "importe_paciente) VALUES (:p, 1, :t, 1, 100, 90, 0, 100, :cob, 0, :pac)")
    async with session_factory() as s:
        presupuesto_id = await _presupuesto(s, await _paciente(s))
        with pytest.raises(IntegrityError):  # cobertura > bruto
            await s.execute(text(sql), {"p": presupuesto_id, "t": seed_ids["tratamiento_id"],
                                        "cob": Decimal("110.00"), "pac": Decimal("-10.00")})
        await s.rollback()
        presupuesto_id = await _presupuesto(s, await _paciente(s, "99000002"))
        with pytest.raises(IntegrityError):  # importe_paciente != bruto - cobertura + diferencial
            await s.execute(text(sql), {"p": presupuesto_id, "t": seed_ids["tratamiento_id"],
                                        "cob": Decimal("90.00"), "pac": Decimal("11.00")})
        await s.rollback()
        presupuesto_id = await _presupuesto(s, await _paciente(s, "99000003"))
        await s.execute(text(sql), {"p": presupuesto_id, "t": seed_ids["tratamiento_id"],
                                    "cob": Decimal("90.00"), "pac": Decimal("10.00")})
        await s.rollback()


@pytest.mark.parametrize("medio,monto", [("transferencia", "0.00"), ("transferencia", "-5.00"), ("efectivo", "5.00")])
async def test_pago_rechaza_monto_no_positivo_y_medio_efectivo(
        session_factory: async_sessionmaker[AsyncSession], medio: str, monto: str) -> None:
    async with session_factory() as s:
        presupuesto_id = await _presupuesto(s, await _paciente(s))
        with pytest.raises(IntegrityError):
            await s.execute(text(
                "INSERT INTO pago_presupuesto (presupuesto_id, medio, monto, estado, fecha_cobro) "
                "VALUES (:p, :m, :mo, 'registrado', :f)"),
                {"p": presupuesto_id, "m": medio, "mo": Decimal(monto), "f": AHORA})
        await s.rollback()


async def test_ficha_unica_por_paciente(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as s:
        paciente_id = await _paciente(s)
        await s.execute(text("INSERT INTO ficha (paciente_id, version) VALUES (:p, 1)"), {"p": paciente_id})
        with pytest.raises(IntegrityError):
            await s.execute(text("INSERT INTO ficha (paciente_id, version) VALUES (:p, 1)"), {"p": paciente_id})
        await s.rollback()


_SQL_PAGO_REF = ("INSERT INTO pago_presupuesto (presupuesto_id, medio, monto, estado, fecha_cobro, referencia, "
                 "anulado_en, anulado_motivo) VALUES (:p, :m, 5, :e, :f, 'MP-SINT-0001', :ae, :am)")


def _params_pago(p: int, medio: str, estado: str) -> dict[str, object]:
    anulado = estado == "anulado"
    return {"p": p, "m": medio, "e": estado, "f": AHORA, "ae": AHORA if anulado else None,
            "am": "motivo sintético" if anulado else None}


async def test_referencia_repetida_entre_registrados_del_mismo_medio_se_rechaza(
        session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as s:
        presupuesto_id = await _presupuesto(s, await _paciente(s))
        await s.execute(text(_SQL_PAGO_REF), _params_pago(presupuesto_id, "mercadopago", "registrado"))
        with pytest.raises(IntegrityError):
            await s.execute(text(_SQL_PAGO_REF), _params_pago(presupuesto_id, "mercadopago", "registrado"))
        await s.rollback()


async def test_referencia_repetida_se_acepta_si_el_otro_esta_anulado_o_el_medio_difiere(
        session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as s:
        presupuesto_id = await _presupuesto(s, await _paciente(s))
        await s.execute(text(_SQL_PAGO_REF), _params_pago(presupuesto_id, "mercadopago", "anulado"))
        await s.execute(text(_SQL_PAGO_REF), _params_pago(presupuesto_id, "mercadopago", "registrado"))
        await s.execute(text(_SQL_PAGO_REF), _params_pago(presupuesto_id, "transferencia", "registrado"))
        await s.rollback()


# --- 1.4 Reversibilidad -----------------------------------------------------------------------------------------

async def test_downgrade_borra_las_cinco_tablas_sin_tocar_las_existentes_y_upgrade_las_recrea(
        session_factory: async_sessionmaker[AsyncSession]) -> None:
    try:
        abajo = alembic("downgrade", "007_turno_origen_ocupacion")
        assert abajo.returncode == 0, abajo.stderr
        async with session_factory() as s:
            presentes = (await s.execute(text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' "
                "AND table_name = ANY(:t)"), {"t": list(TABLAS) + ["turno", "paciente", "pago_sena"]})).scalars().all()
        assert sorted(presentes) == ["paciente", "pago_sena", "turno"]
    finally:
        arriba = alembic("upgrade", "head")
        assert arriba.returncode == 0, arriba.stderr
    async with session_factory() as s:
        n = (await s.execute(text(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' "
            "AND table_name = ANY(:t)"), {"t": list(TABLAS)})).scalar_one()
    assert n == 5
