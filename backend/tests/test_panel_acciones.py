"""C-08 (1.5) y C-11 (9.5, O15): acciones que el servidor informa para cada turno de la agenda. Función pura."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.panel.acciones import acciones_permitidas

BA = ZoneInfo("America/Argentina/Buenos_Aires")
TOL = timedelta(minutes=10)
INICIO = datetime(2031, 8, 4, 9, 0, tzinfo=BA)


def _acciones(estado: str, ahora: datetime, *, permiso: str = "total", inicio: datetime = INICIO) -> list[str]:
    return acciones_permitidas(estado, inicio, ahora, permiso, BA, TOL)  # type: ignore[arg-type]


def test_en_vivo_a_las_8_solo_atendido() -> None:
    assert _acciones("reservado", datetime(2031, 8, 4, 8, 0, tzinfo=BA)) == ["atendido"]


def test_a_las_9_09_59_todavia_no_se_puede_ausente() -> None:
    assert _acciones("reservado", datetime(2031, 8, 4, 9, 9, 59, tzinfo=BA)) == ["atendido"]


def test_a_las_9_10_00_ya_se_puede_ausente() -> None:
    assert _acciones("reservado", datetime(2031, 8, 4, 9, 10, tzinfo=BA)) == ["atendido", "ausente"]


@pytest.mark.parametrize("estado", ["reservado", "confirmado"])
def test_ambos_estados_que_ocupan_agenda_se_tratan_igual(estado: str) -> None:
    assert _acciones(estado, datetime(2031, 8, 4, 9, 30, tzinfo=BA)) == ["atendido", "ausente"]


def test_atendido_aparece_a_las_cero_horas_del_dia_del_turno_y_no_un_segundo_antes() -> None:
    assert _acciones("reservado", datetime(2031, 8, 3, 23, 59, 59, tzinfo=BA)) == []
    assert _acciones("reservado", datetime(2031, 8, 4, 0, 0, 0, tzinfo=BA)) == ["atendido"]


def test_cancelar_aparece_con_24_horas_exactas_y_no_con_23_59() -> None:
    assert _acciones("reservado", INICIO - timedelta(hours=24)) == ["cancelar"]
    assert _acciones("reservado", INICIO - timedelta(hours=23, minutes=59)) == []


def test_con_48_horas_solo_cancelar() -> None:
    assert _acciones("confirmado", INICIO - timedelta(hours=48)) == ["cancelar"]


def test_el_dia_anterior_dentro_de_las_24_horas_no_hay_ninguna() -> None:
    assert _acciones("reservado", datetime(2031, 8, 3, 20, 0, tzinfo=BA)) == []


def test_en_espera_solo_se_puede_cancelar_en_cualquier_momento() -> None:
    assert _acciones("en_espera", INICIO - timedelta(hours=1)) == ["cancelar"]
    assert _acciones("en_espera", INICIO + timedelta(hours=3)) == ["cancelar"]


@pytest.mark.parametrize("estado", ["ausente", "atendido", "cancelado"])
def test_los_estados_finales_no_tienen_acciones(estado: str) -> None:
    assert _acciones(estado, INICIO + timedelta(hours=1)) == []


@pytest.mark.parametrize("estado", ["reservado", "confirmado", "en_espera"])
def test_sin_ningun_permiso_no_hay_acciones(estado: str) -> None:
    assert _acciones(estado, INICIO + timedelta(minutes=20), permiso="ninguno") == []
    assert _acciones(estado, INICIO - timedelta(hours=48), permiso="ninguno") == []


@pytest.mark.parametrize("estado", ["reservado", "confirmado"])
def test_solo_atendido_con_el_turno_de_hoy_iniciado_aunque_total_daria_atendido_y_ausente(estado: str) -> None:
    ahora = datetime(2031, 8, 4, 9, 30, tzinfo=BA)
    assert _acciones(estado, ahora, permiso="total") == ["atendido", "ausente"]
    assert _acciones(estado, ahora, permiso="solo_atendido") == ["atendido"]


def test_solo_atendido_a_48_horas_no_ofrece_nada_aunque_total_daria_cancelar() -> None:
    ahora = INICIO - timedelta(hours=48)
    assert _acciones("reservado", ahora, permiso="total") == ["cancelar"]
    assert _acciones("reservado", ahora, permiso="solo_atendido") == []


def test_solo_atendido_respeta_el_limite_de_las_cero_horas() -> None:
    assert _acciones("reservado", datetime(2031, 8, 3, 23, 59, 59, tzinfo=BA), permiso="solo_atendido") == []
    assert _acciones("reservado", datetime(2031, 8, 4, 0, 0, 0, tzinfo=BA), permiso="solo_atendido") == ["atendido"]


@pytest.mark.parametrize("estado", ["en_espera", "ausente", "atendido", "cancelado"])
def test_solo_atendido_no_ofrece_nada_en_en_espera_ni_en_estados_finales(estado: str) -> None:
    assert _acciones(estado, INICIO + timedelta(hours=1), permiso="solo_atendido") == []
    assert _acciones(estado, INICIO - timedelta(hours=1), permiso="solo_atendido") == []


def test_con_tolerancia_cero_ausente_aparece_a_la_hora_exacta() -> None:
    assert acciones_permitidas("reservado", INICIO, INICIO, "total", BA, timedelta(0)) == ["atendido", "ausente"]
