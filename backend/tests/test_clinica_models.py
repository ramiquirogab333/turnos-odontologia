"""C-11 (1.2): contrato del metadata ORM de los modelos nuevos (R4, R6). Complementa a test_models_metadata.py."""

import pytest
from sqlalchemy import DateTime, Numeric

from app.clinica.models import OdontogramaRegistro, PagoPresupuesto, Presupuesto, PresupuestoLinea
from app.pacientes.models import Ficha

MODELOS = [Ficha, OdontogramaRegistro, Presupuesto, PresupuestoLinea, PagoPresupuesto]


@pytest.mark.parametrize("modelo", MODELOS)
def test_toda_fk_tiene_un_indice_que_empieza_por_su_columna(modelo: type) -> None:
    tabla = modelo.__table__  # type: ignore[attr-defined]
    indexadas = {idx.columns.values()[0].name for idx in tabla.indexes}
    indexadas |= {c.columns.values()[0].name for c in tabla.constraints if c.__class__.__name__ == "UniqueConstraint"}
    indexadas |= {c.name for c in tabla.columns if c.unique}
    for fk in tabla.foreign_keys:
        assert fk.parent.name in indexadas, f"{tabla.name}.{fk.parent.name} sin índice"


@pytest.mark.parametrize("modelo", MODELOS)
def test_fechas_con_zona_y_dinero_numeric(modelo: type) -> None:
    for col in modelo.__table__.columns:  # type: ignore[attr-defined]
        if isinstance(col.type, DateTime):
            assert col.type.timezone is True, f"{col.table.name}.{col.name} sin zona (R4)"
        if col.name in {"monto", "subtotal", "precio_unitario"} or col.name.startswith("importe_"):
            assert isinstance(col.type, Numeric), f"{col.table.name}.{col.name} no es Numeric (R4)"


def test_ficha_es_uno_a_uno_con_paciente() -> None:
    assert Ficha.__table__.c.paciente_id.unique is True
