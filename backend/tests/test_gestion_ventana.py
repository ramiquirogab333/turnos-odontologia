"""C-07 (1.1): regla pura de la ventana de 24 h con `ahora` inyectado (RN-TU-01, RN-TU-02). Sin DB."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.pagos.estados import (
    CancelacionFueraDePlazoError,
    aplicar_transicion,
    dentro_de_ventana,
    limite_cambios,
)

ZONA = ZoneInfo("America/Argentina/Buenos_Aires")
INICIO = datetime(2026, 11, 16, 10, 0, tzinfo=ZONA)


@pytest.mark.parametrize(
    "antes,esperado",
    [
        (timedelta(hours=48), True),
        (timedelta(hours=24), True),  # exactamente 24 h se acepta
        (timedelta(hours=24, seconds=1), True),
        (timedelta(hours=24) - timedelta(seconds=1), False),
        (timedelta(hours=23, minutes=59), False),
        (timedelta(0), False),
        (timedelta(hours=-1), False),  # el inicio ya pasó
    ],
)
def test_dentro_de_ventana_compara_instantes_absolutos(antes: timedelta, esperado: bool) -> None:
    assert dentro_de_ventana(INICIO, INICIO - antes) is esperado


def test_la_ventana_no_depende_de_la_zona_con_que_llegan_los_datetimes() -> None:
    ahora_utc = (INICIO - timedelta(hours=24)).astimezone(timezone.utc)
    assert dentro_de_ventana(INICIO.astimezone(timezone.utc), ahora_utc) is True
    assert dentro_de_ventana(INICIO, ahora_utc + timedelta(seconds=1)) is False


@pytest.mark.parametrize("inicio_ingenuo,ahora_ingenuo", [(True, False), (False, True)])
def test_datetime_sin_zona_es_un_error(inicio_ingenuo: bool, ahora_ingenuo: bool) -> None:
    inicio = INICIO.replace(tzinfo=None) if inicio_ingenuo else INICIO
    ahora = (INICIO - timedelta(days=3))
    ahora = ahora.replace(tzinfo=None) if ahora_ingenuo else ahora
    with pytest.raises(ValueError):
        dentro_de_ventana(inicio, ahora)


def test_limite_cambios_es_24_h_antes_con_el_offset_de_la_clinica() -> None:
    limite = limite_cambios(INICIO.astimezone(timezone.utc), ZONA)
    assert limite.isoformat() == "2026-11-15T10:00:00-03:00"


def test_limite_cambios_cruza_de_dia_y_mes() -> None:
    inicio = datetime(2026, 12, 1, 8, 30, tzinfo=ZONA)
    assert limite_cambios(inicio, ZONA).isoformat() == "2026-11-30T08:30:00-03:00"


def test_limite_cambios_rechaza_datetime_sin_zona() -> None:
    with pytest.raises(ValueError):
        limite_cambios(INICIO.replace(tzinfo=None), ZONA)


def test_aplicar_transicion_usa_la_misma_regla_en_el_borde() -> None:
    # Exactamente 24 h: la cancelación pasa; un segundo menos: se rechaza (misma fuente que dentro_de_ventana).
    ok = aplicar_transicion(
        "reservado", "cancelado", estado_pago="acreditado", inicio=INICIO, ahora=INICIO - timedelta(hours=24)
    )
    assert ok.estado_pago == "a_reembolsar"
    with pytest.raises(CancelacionFueraDePlazoError):
        aplicar_transicion(
            "reservado", "cancelado", estado_pago="acreditado", inicio=INICIO,
            ahora=INICIO - timedelta(hours=24) + timedelta(seconds=1),
        )


def test_en_espera_se_cancela_sin_ventana() -> None:
    r = aplicar_transicion(
        "en_espera", "cancelado", estado_pago="pendiente", inicio=INICIO, ahora=INICIO - timedelta(hours=3)
    )
    assert (r.estado_turno, r.estado_pago) == ("cancelado", "vencido")
