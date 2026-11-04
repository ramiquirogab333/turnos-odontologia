"""Unit C-05 (tarea 1.1): validación en el borde de los esquemas públicos (R15).

Sin base de datos: ejercitan solo Pydantic. Datos 100% sintéticos (R19).
"""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.public.schemas import DisponibilidadPublicaQuery, ReservaPublicaRequest

_FUTURO = datetime.now(timezone.utc) + timedelta(days=3)


def _payload(**override: object) -> dict[str, object]:
    base: dict[str, object] = {
        "nombre": "Carlos Sintético",
        "telefono": "+5491144445555",
        "tratamiento_id": 1,
        "profesional_id": 1,
        "inicio": _FUTURO.isoformat(),
    }
    base.update(override)
    return base


@pytest.mark.parametrize("telefono", ["+5491144445555", "+12025550123", "+442071838750"])
def test_telefono_e164_valido_se_acepta(telefono: str) -> None:
    assert ReservaPublicaRequest(**_payload(telefono=telefono)).telefono == telefono


@pytest.mark.parametrize(
    "telefono",
    ["1234", "5491144445555", "+0123456789", "+54 9 11 4444 5555", "+549114444abcd", "+", "", "+5491144445555999"],
)
def test_telefono_invalido_se_rechaza_en_el_campo_telefono(telefono: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        ReservaPublicaRequest(**_payload(telefono=telefono))
    assert exc_info.value.errors()[0]["loc"] == ("telefono",)


def test_nombre_completo_es_el_unico_dato_personal_requerido() -> None:
    """Spec: el paciente ingresa solo nombre + teléfono (sin apellido ni DNI)."""
    req = ReservaPublicaRequest(**_payload())
    assert req.nombre == "Carlos Sintético"


@pytest.mark.parametrize("nombre", ["", "   ", "x" * 201])
def test_nombre_vacio_o_excesivo_se_rechaza(nombre: str) -> None:
    with pytest.raises(ValidationError):
        ReservaPublicaRequest(**_payload(nombre=nombre))


def test_nombre_se_normaliza_sin_espacios_laterales() -> None:
    assert ReservaPublicaRequest(**_payload(nombre="  Ana Sintética ")).nombre == "Ana Sintética"


def test_campo_extra_se_rechaza() -> None:
    with pytest.raises(ValidationError):
        ReservaPublicaRequest(**_payload(dni="12345678"))


def test_inicio_pasado_se_rechaza() -> None:
    with pytest.raises(ValidationError):
        ReservaPublicaRequest(**_payload(inicio=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()))


def test_inicio_naive_se_interpreta_en_la_zona_horaria_de_la_clinica() -> None:
    """Un inicio sin offset es hora local de la clínica (APP_TZ), no UTC."""
    local = (datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")) + timedelta(days=3)).replace(
        hour=10, minute=0, second=0, microsecond=0, tzinfo=None
    )
    req = ReservaPublicaRequest(**_payload(inicio=local.isoformat()))
    assert req.inicio.utcoffset() == timedelta(hours=-3)
    assert req.inicio.hour == 10


def test_query_disponibilidad_valida_rango_coherente() -> None:
    q = DisponibilidadPublicaQuery(
        profesional_id=1, tratamiento_id=1, desde=date(2030, 1, 7), hasta=date(2030, 1, 7)
    )
    assert q.desde == q.hasta


def test_query_disponibilidad_rechaza_hasta_anterior_a_desde() -> None:
    with pytest.raises(ValidationError):
        DisponibilidadPublicaQuery(
            profesional_id=1, tratamiento_id=1, desde=date(2030, 1, 8), hasta=date(2030, 1, 7)
        )


def test_query_disponibilidad_rechaza_rango_mayor_a_31_dias() -> None:
    with pytest.raises(ValidationError):
        DisponibilidadPublicaQuery(
            profesional_id=1, tratamiento_id=1, desde=date(2030, 1, 1), hasta=date(2030, 3, 1)
        )
