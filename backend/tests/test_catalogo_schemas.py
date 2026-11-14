"""C-14 (2.1; D4, D5, O12): validaciones de borde del catálogo (R15). Unitarios, sin base de datos."""

from datetime import time
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.catalogo.schemas import (
    DURACION_MAX,
    DURACION_MIN,
    DURACION_PASO,
    PRECIO_MAX,
    DisponibilidadCreate,
    DisponibilidadRead,
    ProfesionalCreate,
    ProfesionalRead,
    ProfesionalUpdate,
    SillonCreate,
    SillonUpdate,
    TratamientoCreate,
    TratamientoRead,
    TratamientoUpdate,
)
from app.models.core import Disponibilidad
from app.turnos.models import Profesional, Tratamiento


def _campos_con_error(exc: ValidationError) -> set[str]:
    return {str(e["loc"][-1]) for e in exc.errors()}


def _tratamiento(**sobre: object) -> TratamientoCreate:
    datos: dict[str, object] = {"nombre": "Limpieza dental", "duracion_minutos": 30, "precio_base": "5000.00", **sobre}
    return TratamientoCreate(**datos)  # type: ignore[arg-type]


def test_las_constantes_documentan_los_topes_aprobados() -> None:
    assert (DURACION_MIN, DURACION_MAX, DURACION_PASO) == (5, 480, 5)
    assert PRECIO_MAX == Decimal("99999999.99")


@pytest.mark.parametrize("minutos", [5, 30, 45, 480])
def test_las_duraciones_validas_incluidos_los_limites_se_aceptan(minutos: int) -> None:
    assert _tratamiento(duracion_minutos=minutos).duracion_minutos == minutos


@pytest.mark.parametrize("minutos", [0, -5, 7, 4, 485, 481, 1000])
def test_las_duraciones_fuera_de_rango_o_que_no_son_multiplo_de_5_se_rechazan_nombrando_el_campo(minutos: int) -> None:
    with pytest.raises(ValidationError) as exc:
        _tratamiento(duracion_minutos=minutos)
    assert _campos_con_error(exc.value) == {"duracion_minutos"}


@pytest.mark.parametrize("precio", ["0", "0.00", "5000.5", "99999999.99"])
def test_los_precios_validos_incluido_el_maximo_de_la_columna_se_aceptan(precio: str) -> None:
    assert _tratamiento(precio_base=precio).precio_base == Decimal(precio)


@pytest.mark.parametrize("precio", ["100000000.00", "-1", "-0.01", "1.005", "NaN", "Infinity"])
def test_los_precios_negativos_mayores_al_maximo_o_con_mas_de_dos_decimales_se_rechazan_nombrando_el_campo(precio: str) -> None:
    with pytest.raises(ValidationError) as exc:
        _tratamiento(precio_base=precio)
    assert _campos_con_error(exc.value) == {"precio_base"}


def test_el_nombre_se_recorta_antes_de_validar_en_alta_y_edicion() -> None:
    assert _tratamiento(nombre="  Limpieza dental  ").nombre == "Limpieza dental"
    assert TratamientoUpdate(nombre="  Empaste ").nombre == "Empaste"
    assert ProfesionalCreate(nombre=" Dra. Ana Ficticia ", matricula=" MP-99001 ").matricula == "MP-99001"
    assert SillonCreate(nombre="  Sillón 1 ").nombre == "Sillón 1"
    with pytest.raises(ValidationError) as exc:
        _tratamiento(nombre="    ")
    assert _campos_con_error(exc.value) == {"nombre"}


def test_activo_acepta_booleanos_y_rechaza_cualquier_otra_cosa() -> None:
    assert TratamientoUpdate(activo=False).activo is False
    assert ProfesionalUpdate(activo=True).activo is True
    assert _tratamiento().activo is True  # un tratamiento nuevo nace activo
    assert _tratamiento(activo=False).activo is False
    for invalido in ("quizas", [], {"x": 1}):
        with pytest.raises(ValidationError) as exc:
            ProfesionalUpdate(activo=invalido)  # type: ignore[arg-type]
        assert _campos_con_error(exc.value) == {"activo"}


def test_el_update_parcial_distingue_lo_no_enviado_de_lo_enviado() -> None:
    assert TratamientoUpdate(activo=False).model_dump(exclude_unset=True) == {"activo": False}
    assert TratamientoUpdate(duracion_minutos=60).model_dump(exclude_unset=True) == {"duracion_minutos": 60}
    with pytest.raises(ValidationError):
        SillonUpdate(estado="roto")


def test_los_read_exponen_activo_leyendo_is_active_del_modelo() -> None:
    tratamiento = Tratamiento(nombre="Limpieza", duracion_minutos=30, precio_base=Decimal("1000.00"), is_active=False)
    tratamiento.id = 1
    assert TratamientoRead.model_validate(tratamiento).model_dump()["activo"] is False
    profesional = Profesional(nombre="Dra. Ana Ficticia", matricula="MP-99001", especialidad="", is_active=True)
    profesional.id = 2
    assert ProfesionalRead.model_validate(profesional).model_dump()["activo"] is True
    franja = Disponibilidad(profesional_id=2, dia_semana=0, hora_inicio=time(9), hora_fin=time(13), is_active=True)
    franja.id = 3
    assert DisponibilidadRead.model_validate(franja).model_dump()["activo"] is True
    assert "is_active" not in TratamientoRead.model_validate(tratamiento).model_dump()


def test_el_alta_de_franja_valida_el_orden_de_las_horas_y_acepta_activo() -> None:
    ok = DisponibilidadCreate(profesional_id=1, dia_semana=1, hora_inicio=time(9), hora_fin=time(13))
    assert ok.activo is True
    with pytest.raises(ValidationError) as exc:
        DisponibilidadCreate(profesional_id=1, dia_semana=1, hora_inicio=time(13), hora_fin=time(13))
    assert _campos_con_error(exc.value) == {"hora_fin"}
