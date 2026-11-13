"""C-13 (6.1, D7): cursor keyset opaco y validación de ``AuditoriaQuery`` (R15). Datos sintéticos."""

import base64
import json
from datetime import date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.plataforma.cursor import CursorInvalidoError, codificar_cursor, decodificar_cursor
from app.plataforma.schemas import AuditoriaQuery
from app.plataforma.tipos_auditoria import TIPOS

T = datetime(2026, 11, 12, 15, 30, 45, 123456, tzinfo=timezone.utc)
HOY = date(2026, 11, 13)


def test_el_cursor_codifica_y_decodifica_sin_perder_el_instante_ni_el_id() -> None:
    cursor = codificar_cursor(T, 987654321)
    assert cursor.isascii() and "=" not in cursor and "+" not in cursor and "/" not in cursor  # base64url sin relleno
    assert decodificar_cursor(cursor) == (T, 987654321)


def test_dos_cursores_distintos_se_distinguen_y_el_instante_con_zona_se_conserva() -> None:
    otro = T.astimezone(timezone(timedelta(hours=-3)))
    assert decodificar_cursor(codificar_cursor(otro, 1)) == (T, 1)  # mismo instante
    assert codificar_cursor(T, 1) != codificar_cursor(T, 2)


@pytest.mark.parametrize("cursor", [
    "",
    "no-es-base64-%%%",
    base64.urlsafe_b64encode(b"esto no es json").decode().rstrip("="),
    base64.urlsafe_b64encode(json.dumps({"t": "2026-11-12T15:30:00+00:00"}).encode()).decode().rstrip("="),  # sin id
    base64.urlsafe_b64encode(json.dumps({"t": "ayer", "id": 3}).encode()).decode().rstrip("="),  # instante ilegible
    base64.urlsafe_b64encode(json.dumps({"t": "2026-11-12T15:30:00", "id": 3}).encode()).decode().rstrip("="),  # sin zona
    base64.urlsafe_b64encode(json.dumps({"t": "2026-11-12T15:30:00+00:00", "id": "3"}).encode()).decode().rstrip("="),
    base64.urlsafe_b64encode(json.dumps({"t": "2026-11-12T15:30:00+00:00", "id": -5}).encode()).decode().rstrip("="),
    base64.urlsafe_b64encode(json.dumps([1, 2]).encode()).decode().rstrip("="),
])
def test_un_cursor_ilegible_o_manipulado_es_un_error(cursor: str) -> None:
    with pytest.raises(CursorInvalidoError):
        decodificar_cursor(cursor)


def test_la_query_por_defecto_son_los_ultimos_siete_dias_y_cincuenta_por_pagina() -> None:
    q = AuditoriaQuery()
    assert q.rango(HOY) == (date(2026, 11, 7), HOY) and q.por_pagina == 50
    assert (q.entidad, q.entidad_id, q.usuario_id, q.tipo, q.cursor) == (None,) * 5


def test_con_solo_desde_o_solo_hasta_se_completa_con_hoy_o_siete_dias_antes() -> None:
    assert AuditoriaQuery(desde=date(2026, 11, 1)).rango(HOY) == (date(2026, 11, 1), HOY)
    assert AuditoriaQuery(hasta=date(2026, 11, 10)).rango(HOY) == (date(2026, 11, 4), date(2026, 11, 10))


def test_desde_posterior_a_hasta_es_error() -> None:
    with pytest.raises(ValidationError):
        AuditoriaQuery(desde=date(2026, 11, 10), hasta=date(2026, 11, 9))
    with pytest.raises(ValueError):  # con un solo extremo, el error aparece al resolver contra "hoy"
        AuditoriaQuery(desde=date(2026, 11, 20)).rango(HOY)


def test_un_rango_de_400_dias_es_error_y_uno_de_366_es_valido() -> None:
    with pytest.raises(ValidationError):
        AuditoriaQuery(desde=date(2025, 10, 1), hasta=date(2026, 11, 5))
    ok = AuditoriaQuery(desde=date(2025, 11, 12), hasta=date(2026, 11, 13))  # 366 días
    assert (ok.hasta - ok.desde).days == 366  # type: ignore[operator]


def test_un_tipo_fuera_del_catalogo_es_error_y_el_mensaje_lista_los_validos() -> None:
    with pytest.raises(ValidationError) as exc:
        AuditoriaQuery(tipo="inventado")
    assert "cierre_caja" in str(exc.value) and "otro" in str(exc.value)
    assert all(AuditoriaQuery(tipo=codigo).tipo == codigo for codigo in TIPOS)


@pytest.mark.parametrize("campos", [{"por_pagina": 0}, {"por_pagina": 101}, {"usuario_id": 0}, {"entidad": "x"},
                                    {"entidad_id": ""}, {"campo_desconocido": 1}])
def test_los_limites_y_los_campos_desconocidos_se_rechazan(campos: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        AuditoriaQuery(**campos)  # type: ignore[arg-type]
