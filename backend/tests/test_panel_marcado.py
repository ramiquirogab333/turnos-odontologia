"""C-08 (1.2, O14, RN-TU-12): cuándo se habilita marcar ausente y atendido. Funciones puras, sin base."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.pagos.estados import ausente_habilitado_desde, atendido_habilitado_desde

BA = ZoneInfo("America/Argentina/Buenos_Aires")


def test_ausente_se_habilita_al_inicio_mas_la_tolerancia() -> None:
    inicio = datetime(2031, 6, 2, 10, 0, tzinfo=BA)
    assert ausente_habilitado_desde(inicio, timedelta(minutes=10)) == datetime(2031, 6, 2, 10, 10, tzinfo=BA)


def test_ausente_con_tolerancia_cero_se_habilita_al_inicio() -> None:
    inicio = datetime(2031, 6, 2, 10, 0, tzinfo=BA)
    assert ausente_habilitado_desde(inicio, timedelta(0)) == inicio


def test_ausente_conserva_el_instante_en_otra_zona() -> None:
    inicio = datetime(2031, 6, 2, 13, 0, tzinfo=timezone.utc)  # 10:00 en Buenos Aires
    assert ausente_habilitado_desde(inicio, timedelta(minutes=10)) == datetime(2031, 6, 2, 10, 10, tzinfo=BA)


def test_atendido_se_habilita_a_las_cero_horas_locales_del_dia_del_turno() -> None:
    inicio = datetime(2031, 6, 2, 10, 0, tzinfo=BA)
    assert atendido_habilitado_desde(inicio, BA) == datetime(2031, 6, 2, 0, 0, tzinfo=BA)


def test_atendido_usa_la_fecha_local_aunque_la_fecha_utc_sea_otra() -> None:
    # 02:30 UTC del 3 de junio es el 2 de junio a las 23:30 en Buenos Aires: el día del turno es el 2.
    inicio = datetime(2031, 6, 3, 2, 30, tzinfo=timezone.utc)
    assert inicio.date().day == 3
    assert atendido_habilitado_desde(inicio, BA) == datetime(2031, 6, 2, 0, 0, tzinfo=BA)


def test_atendido_a_las_cero_horas_exactas_del_turno() -> None:
    inicio = datetime(2031, 6, 2, 0, 0, tzinfo=BA)
    assert atendido_habilitado_desde(inicio, BA) == inicio


@pytest.mark.parametrize("llamada", [
    lambda naive: ausente_habilitado_desde(naive, timedelta(minutes=10)),
    lambda naive: atendido_habilitado_desde(naive, BA),
])
def test_un_datetime_sin_zona_es_un_error(llamada) -> None:
    with pytest.raises(ValueError):
        llamada(datetime(2031, 6, 2, 10, 0))
