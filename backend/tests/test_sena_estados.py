"""C-06 (2.2): máquina de estados del turno y efectos sobre la seña. Sin DB (RN-SN-02/04/05, RN-TU-01, R9)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.pagos.estados import (
    CancelacionFueraDePlazoError,
    TransicionInvalidaError,
    aplicar_transicion,
    transicionar,
)

INICIO = datetime(2031, 3, 3, 13, 0, tzinfo=timezone.utc)

PERMITIDAS = [
    ("en_espera", "reservado"), ("en_espera", "cancelado"),
    ("reservado", "confirmado"), ("reservado", "cancelado"), ("reservado", "ausente"), ("reservado", "atendido"),
    ("confirmado", "cancelado"), ("confirmado", "ausente"), ("confirmado", "atendido"),
]
PROHIBIDAS = [
    ("en_espera", "ausente"), ("en_espera", "atendido"), ("en_espera", "confirmado"),
    ("reservado", "en_espera"), ("confirmado", "reservado"), ("confirmado", "en_espera"),
    ("atendido", "reservado"), ("atendido", "cancelado"), ("atendido", "ausente"),
    ("cancelado", "reservado"), ("cancelado", "en_espera"), ("ausente", "atendido"), ("ausente", "reservado"),
]


@pytest.mark.parametrize("actual,destino", PERMITIDAS)
def test_transiciones_permitidas(actual: str, destino: str) -> None:
    assert transicionar(actual, destino) == destino


@pytest.mark.parametrize("actual,destino", PROHIBIDAS)
def test_transiciones_prohibidas(actual: str, destino: str) -> None:
    with pytest.raises(TransicionInvalidaError):
        transicionar(actual, destino)


@pytest.mark.parametrize("final", ["atendido", "cancelado", "ausente"])
def test_los_estados_finales_no_salen(final: str) -> None:
    for destino in ("en_espera", "reservado", "confirmado", "cancelado", "ausente", "atendido"):
        with pytest.raises(TransicionInvalidaError):
            transicionar(final, destino)


@pytest.mark.parametrize("actual", ["reservado", "confirmado"])
def test_ausente_con_sena_acreditada_queda_no_reembolsado(actual: str) -> None:
    r = aplicar_transicion(actual, "ausente", estado_pago="acreditado", inicio=INICIO, ahora=INICIO)
    assert (r.estado_turno, r.estado_pago) == ("ausente", "no_reembolsado")  # R9, RN-SN-02


def test_ausente_sin_sena_no_toca_pago() -> None:
    r = aplicar_transicion("reservado", "ausente", estado_pago=None, inicio=INICIO, ahora=INICIO)
    assert r.estado_pago is None


def test_cancelado_con_48h_y_sena_acreditada_pasa_a_reembolsar() -> None:
    r = aplicar_transicion("reservado", "cancelado", estado_pago="acreditado",
                           inicio=INICIO, ahora=INICIO - timedelta(hours=48))
    assert (r.estado_turno, r.estado_pago) == ("cancelado", "a_reembolsar")  # RN-SN-04


def test_cancelado_con_exactamente_24h_se_acepta() -> None:
    r = aplicar_transicion("confirmado", "cancelado", estado_pago="acreditado",
                           inicio=INICIO, ahora=INICIO - timedelta(hours=24))
    assert r.estado_pago == "a_reembolsar"


def test_cancelado_con_23h59_se_rechaza() -> None:
    with pytest.raises(CancelacionFueraDePlazoError):
        aplicar_transicion("reservado", "cancelado", estado_pago="acreditado",
                           inicio=INICIO, ahora=INICIO - timedelta(hours=23, minutes=59))


def test_cancelado_sin_sena_tambien_respeta_las_24h() -> None:
    with pytest.raises(CancelacionFueraDePlazoError):
        aplicar_transicion("reservado", "cancelado", estado_pago=None,
                           inicio=INICIO, ahora=INICIO - timedelta(hours=2))
    r = aplicar_transicion("reservado", "cancelado", estado_pago=None,
                           inicio=INICIO, ahora=INICIO - timedelta(hours=30))
    assert r.estado_pago is None


def test_en_espera_cancelado_con_pago_pendiente_pasa_a_vencido_sin_ventana() -> None:
    r = aplicar_transicion("en_espera", "cancelado", estado_pago="pendiente",
                           inicio=INICIO, ahora=INICIO - timedelta(minutes=5))
    assert (r.estado_turno, r.estado_pago) == ("cancelado", "vencido")


def test_en_espera_a_reservado_no_cambia_el_pago_aqui() -> None:
    """La única vía a reservado es la acreditación (servicio acreditar_pago), que maneja el pago."""
    r = aplicar_transicion("en_espera", "reservado", estado_pago="pendiente", inicio=INICIO, ahora=INICIO)
    assert r.estado_pago is None


# --- C-12 (5.2): plazo para deshacer un atendido ----------------------------------------------------------------

def test_deshacer_habilitado_hasta_es_el_inicio_mas_siete_dias() -> None:
    from app.pagos.estados import VENTANA_DESHACER_ATENDIDO, deshacer_habilitado_hasta

    assert VENTANA_DESHACER_ATENDIDO == timedelta(days=7)
    assert deshacer_habilitado_hasta(INICIO) == INICIO + timedelta(days=7)


def test_exactamente_siete_dias_se_acepta_y_un_segundo_despues_no() -> None:
    from app.pagos.estados import deshacer_dentro_de_plazo

    limite = INICIO + timedelta(days=7)
    assert deshacer_dentro_de_plazo(INICIO, limite) is True
    assert deshacer_dentro_de_plazo(INICIO, limite + timedelta(seconds=1)) is False
    assert deshacer_dentro_de_plazo(INICIO, INICIO + timedelta(hours=26)) is True
    assert deshacer_dentro_de_plazo(INICIO, INICIO - timedelta(hours=1)) is True  # marcado antes de su hora


def test_el_plazo_exige_zona_horaria() -> None:
    from app.pagos.estados import deshacer_dentro_de_plazo, deshacer_habilitado_hasta

    with pytest.raises(ValueError):
        deshacer_habilitado_hasta(datetime(2031, 3, 3, 13, 0))
    with pytest.raises(ValueError):
        deshacer_dentro_de_plazo(INICIO, datetime(2031, 3, 3, 13, 0))


@pytest.mark.parametrize("final", ["atendido", "ausente", "cancelado"])
def test_la_via_general_sigue_sin_salida_desde_los_estados_finales_incluido_atendido_a_reservado(final: str) -> None:
    for destino in ("reservado", "en_espera"):
        with pytest.raises(TransicionInvalidaError):
            transicionar(final, destino)
