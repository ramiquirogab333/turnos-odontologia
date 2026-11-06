"""RED: metadata contract for turnos models (R4/R6). Fails until models exist."""

from sqlalchemy import DateTime, Numeric


def test_fk_columns_have_indexes() -> None:
    from app.turnos.models import Turno

    indexed = {c.name for idx in Turno.__table__.indexes for c in idx.columns}
    for fk_col in ("profesional_id", "sillon_id", "tratamiento_id"):
        assert fk_col in indexed, f"FK sin indice: {fk_col}"


def test_composite_agenda_indexes_exist() -> None:
    from app.turnos.models import Turno

    pairs = [{c.name for c in idx.columns} for idx in Turno.__table__.indexes]
    assert {"profesional_id", "inicio"} in pairs
    assert {"sillon_id", "inicio"} in pairs


def test_tz_aware_and_money_types() -> None:
    from app.turnos.models import Tratamiento, Turno

    assert isinstance(Turno.__table__.c.inicio.type, DateTime)
    assert Turno.__table__.c.inicio.type.timezone is True
    assert isinstance(Turno.__table__.c.fin.type, DateTime)
    assert Turno.__table__.c.fin.type.timezone is True
    assert isinstance(Tratamiento.__table__.c.precio_base.type, Numeric)
    assert Tratamiento.__table__.c.precio_base.type.precision == 10
    assert Tratamiento.__table__.c.precio_base.type.scale == 2


def test_estado_check_and_sillon_not_null() -> None:
    from sqlalchemy import CheckConstraint

    from app.turnos.models import Turno

    assert Turno.__table__.c.sillon_id.nullable is False
    assert Turno.__table__.c.profesional_id.nullable is False
    assert Turno.__table__.c.tratamiento_id.nullable is False
    checks = [str(c.sqltext) for c in Turno.__table__.constraints if isinstance(c, CheckConstraint)]
    assert any("estado" in sql for sql in checks), "falta CHECK de estado"


def test_tratamiento_checks() -> None:
    from sqlalchemy import CheckConstraint

    from app.turnos.models import Tratamiento

    checks = [str(c.sqltext) for c in Tratamiento.__table__.constraints if isinstance(c, CheckConstraint)]
    assert any("duracion_minutos" in sql for sql in checks)
    assert any("precio_base" in sql for sql in checks)


def test_pago_sena_fk_indexes_y_tipos_de_dinero() -> None:
    """C-06 (R4/R6): FK de pago_sena indexadas, monto NUMERIC y fechas con zona horaria."""
    from app.pagos.models import ConfiguracionSena, PagoSena

    indexados = {c.name for idx in PagoSena.__table__.indexes for c in idx.columns}
    assert {"turno_id", "acreditado_por_usuario_id"} <= indexados
    assert isinstance(PagoSena.__table__.c.monto.type, Numeric)
    assert (PagoSena.__table__.c.monto.type.precision, PagoSena.__table__.c.monto.type.scale) == (10, 2)
    assert PagoSena.__table__.c.vence_en.type.timezone is True
    assert isinstance(ConfiguracionSena.__table__.c.sena_porcentaje.type, Numeric)


def test_turno_expone_en_espera_vence_en_con_zona_horaria() -> None:
    from app.turnos.models import Turno

    assert Turno.__table__.c.en_espera_vence_en.type.timezone is True
    assert Turno.__table__.c.en_espera_vence_en.nullable is True
