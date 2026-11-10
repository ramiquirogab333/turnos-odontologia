"""C-11 (2.3): tabla de transiciones del presupuesto, pura, sin base."""

import itertools

import pytest

from app.clinica.estados import ESTADOS, TRANSICIONES, validar_transicion
from app.pagos.estados import TransicionInvalidaError

VALIDAS = [
    ("borrador", "presentado"), ("borrador", "anulado"),
    ("presentado", "aceptado"), ("presentado", "rechazado"), ("presentado", "anulado"),
    ("aceptado", "anulado"),
]


@pytest.mark.parametrize("actual,destino", VALIDAS)
def test_las_seis_transiciones_validas_se_aceptan(actual: str, destino: str) -> None:
    validar_transicion(actual, destino)  # no lanza


@pytest.mark.parametrize("actual,destino", [p for p in itertools.product(ESTADOS, ESTADOS) if p not in VALIDAS])
def test_toda_otra_combinacion_es_invalida(actual: str, destino: str) -> None:
    with pytest.raises(TransicionInvalidaError) as exc:
        validar_transicion(actual, destino)
    assert (exc.value.actual, exc.value.destino) == (actual, destino)


def test_rechazado_y_anulado_son_finales() -> None:
    assert TRANSICIONES.get("rechazado", frozenset()) == frozenset()
    assert TRANSICIONES.get("anulado", frozenset()) == frozenset()


def test_hay_exactamente_cinco_estados_y_seis_transiciones() -> None:
    assert len(ESTADOS) == 5
    assert sum(len(v) for v in TRANSICIONES.values()) == 6


def test_estado_desconocido_es_invalido() -> None:
    with pytest.raises(TransicionInvalidaError):
        validar_transicion("fantasma", "presentado")
