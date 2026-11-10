"""C-11 (2.4): esquemas Pydantic de entrada y salida (R15), sin base. Datos sintéticos (R19)."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.clinica.schemas import (
    AnulacionIn,
    LineaIn,
    LoteOdontogramaIn,
    PagoCreate,
    PresupuestoCreate,
    PresupuestoOut,
    PresupuestoVistaClinicaOut,
    TransicionIn,
)
from app.pacientes.schemas import FichaUpdate, PacienteCreate, PacienteOut, PacienteVistaClinicaOut

PACIENTE = {"nombre": "Lucía", "apellido": "Ejemplo", "dni": "99000001", "telefono": "+5491100000001"}


@pytest.mark.parametrize("dni,ok", [("9900001", True), ("99000001", True), ("990000", False), ("990000012", False),
                                    ("9900000a", False), ("", False)])
def test_dni_de_7_u_8_digitos(dni: str, ok: bool) -> None:
    if ok:
        assert PacienteCreate(**{**PACIENTE, "dni": dni}).dni == dni
    else:
        with pytest.raises(ValidationError):
            PacienteCreate(**{**PACIENTE, "dni": dni})


@pytest.mark.parametrize("tel,ok", [("+5491100000001", True), ("5491100000001", False), ("+0123", False),
                                    ("+54 911", False)])
def test_telefono_e164(tel: str, ok: bool) -> None:
    if ok:
        PacienteCreate(**{**PACIENTE, "telefono": tel})
    else:
        with pytest.raises(ValidationError):
            PacienteCreate(**{**PACIENTE, "telefono": tel})


def test_paciente_rechaza_campos_extra() -> None:
    with pytest.raises(ValidationError):
        PacienteCreate(**PACIENTE, notas="no existe")  # type: ignore[call-arg]


@pytest.mark.parametrize("largo,ok", [(2000, True), (2001, False), (0, True)])
def test_textos_de_ficha_hasta_2000(largo: int, ok: bool) -> None:
    datos = {"alergias": "a" * largo, "medicacion": "", "antecedentes_medicos": "", "observaciones": "", "version": 0}
    if ok:
        assert len(FichaUpdate(**datos).alergias) == largo
    else:
        with pytest.raises(ValidationError):
            FichaUpdate(**datos)


def test_ficha_exige_version_no_negativa() -> None:
    base: dict[str, Any] = {"alergias": "", "medicacion": "", "antecedentes_medicos": "", "observaciones": ""}
    with pytest.raises(ValidationError):
        FichaUpdate(**base, version=-1)
    with pytest.raises(ValidationError):
        FichaUpdate(**base)


def _lote(n: int) -> dict[str, Any]:
    return {"registros": [{"pieza": 16, "cara": "O", "estado": "caries"} for _ in range(n)]}


@pytest.mark.parametrize("n,ok", [(0, False), (1, True), (64, True), (65, False)])
def test_lote_de_odontograma_de_1_a_64(n: int, ok: bool) -> None:
    if ok:
        assert len(LoteOdontogramaIn(**_lote(n)).registros) == n
    else:
        with pytest.raises(ValidationError):
            LoteOdontogramaIn(**_lote(n))


@pytest.mark.parametrize("registro", [
    {"pieza": 19, "estado": "ausente"}, {"pieza": 56, "estado": "ausente"}, {"pieza": 16, "estado": "caries"},
    {"pieza": 16, "cara": "O", "estado": "corona"}, {"pieza": 16, "cara": "X", "estado": "caries"},
    {"pieza": 16, "estado": "ausente", "nota": "n" * 501}, {"pieza": 16, "estado": "ausente", "extra": 1}])
def test_registro_invalido_rechazado_en_el_borde(registro: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        LoteOdontogramaIn(registros=[registro])


@pytest.mark.parametrize("n,ok", [(0, False), (1, True), (50, True), (51, False)])
def test_lineas_de_presupuesto_de_1_a_50(n: int, ok: bool) -> None:
    lineas = [{"tratamiento_id": 1, "cantidad": 1} for _ in range(n)]
    if ok:
        assert len(PresupuestoCreate(lineas=lineas).lineas) == n
    else:
        with pytest.raises(ValidationError):
            PresupuestoCreate(lineas=lineas)


@pytest.mark.parametrize("cantidad,ok", [(0, False), (1, True), (99, True), (100, False)])
def test_cantidad_de_1_a_99(cantidad: int, ok: bool) -> None:
    if ok:
        assert LineaIn(tratamiento_id=1, cantidad=cantidad).cantidad == cantidad
    else:
        with pytest.raises(ValidationError):
            LineaIn(tratamiento_id=1, cantidad=cantidad)


@pytest.mark.parametrize("extra", ["importe_paciente", "precio_unitario", "importe_bruto", "cobertura_porcentaje"])
def test_el_cliente_no_puede_enviar_importes(extra: str) -> None:
    with pytest.raises(ValidationError):
        LineaIn(tratamiento_id=1, cantidad=1, **{extra: "1.00"})  # type: ignore[arg-type]


def test_emitir_factura_se_rechaza() -> None:
    with pytest.raises(ValidationError):
        TransicionIn(emitir_factura=True)  # type: ignore[call-arg]
    TransicionIn()  # el cuerpo vacío sí


@pytest.mark.parametrize("motivo,ok", [("ab", False), ("abc", True), ("m" * 300, True), ("m" * 301, False)])
def test_motivo_de_anulacion_3_a_300(motivo: str, ok: bool) -> None:
    if ok:
        assert AnulacionIn(motivo=motivo).motivo == motivo
    else:
        with pytest.raises(ValidationError):
            AnulacionIn(motivo=motivo)


def test_motivo_con_espacios_se_recorta_antes_de_validar() -> None:
    with pytest.raises(ValidationError):
        AnulacionIn(motivo="  a  ")


@pytest.mark.parametrize("monto,ok", [("1500.00", True), ("0.01", True), ("0", False), ("-5.00", False),
                                      ("10.123", False)])
def test_monto_del_pago_positivo_con_dos_decimales(monto: str, ok: bool) -> None:
    datos = {"medio": "transferencia", "monto": monto}
    if ok:
        assert PagoCreate(**datos).monto == Decimal(monto)
    else:
        with pytest.raises(ValidationError):
            PagoCreate(**datos)


def test_pago_rechaza_medio_efectivo_y_fecha_sin_zona() -> None:
    with pytest.raises(ValidationError):
        PagoCreate(medio="efectivo", monto="5.00")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        PagoCreate(medio="transferencia", monto="5.00", fecha_cobro=datetime(2031, 1, 1))
    PagoCreate(medio="transferencia", monto="5.00", fecha_cobro=datetime(2031, 1, 1, tzinfo=timezone.utc))


# --- Esquemas de salida por rol (O3, D2) ---------------------------------------------------------------------

def test_vista_clinica_del_paciente_tiene_exactamente_los_campos_permitidos() -> None:
    assert set(PacienteVistaClinicaOut.model_fields) == {
        "id", "nombre", "apellido", "dni", "obra_social", "numero_afiliado"}


def test_paciente_completo_no_se_filtra_al_construir_la_vista_clinica() -> None:
    completo = PacienteOut(id=1, nombre="Lucía", apellido="Ejemplo", dni="99000001", telefono="+5491100000001",
                           email="lucia@ejemplo.test", obra_social=None, numero_afiliado="SM-SINT-0001")
    vista = PacienteVistaClinicaOut.model_validate(completo, from_attributes=True)
    volcado = vista.model_dump()
    assert "telefono" not in volcado and "email" not in volcado
    assert volcado["dni"] == "99000001" and volcado["numero_afiliado"] == "SM-SINT-0001"


def test_vista_clinica_del_presupuesto_no_tiene_pagos_ni_saldo() -> None:
    assert not {"pagos", "total_pagado", "saldo"} & set(PresupuestoVistaClinicaOut.model_fields)
    assert {"pagos", "total_pagado", "saldo"} <= set(PresupuestoOut.model_fields)


def test_presupuesto_completo_no_se_filtra_a_la_vista_clinica() -> None:
    completo = PresupuestoOut(
        id=1, paciente_id=1, obra_social=None, estado="aceptado", subtotal=Decimal("100.00"),
        cobertura_total=Decimal("0.00"), diferencial_total=Decimal("0.00"), total_paciente=Decimal("100.00"),
        notas="", presentado_en=None, resuelto_en=None, anulado_en=None, anulado_motivo=None,
        created_at=datetime(2031, 1, 1, tzinfo=timezone.utc), lineas=[], pagos=[],
        total_pagado=Decimal("40.00"), saldo=Decimal("60.00"))
    volcado = PresupuestoVistaClinicaOut.model_validate(completo, from_attributes=True).model_dump(mode="json")
    assert not {"pagos", "total_pagado", "saldo"} & set(volcado)
    assert volcado["total_paciente"] == "100.00"
