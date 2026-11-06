"""C-07 (1.2): puerto de eventos para C-09/C-10. Sin PII (R19, Ley 25.326). Sin DB."""

import dataclasses
import logging
from datetime import datetime, timedelta, timezone

import pytest

from app.gestion.eventos import EventoTurno, NotificadorNulo

INICIO = datetime(2026, 11, 16, 13, 0, tzinfo=timezone.utc)
PROHIBIDOS = ("nombre", "telefono", "contacto", "email", "paciente", "codigo")


def _cancelado() -> EventoTurno:
    return EventoTurno(
        tipo="turno_cancelado", turno_id=41, profesional_id=7, inicio_anterior=INICIO,
        fin_anterior=INICIO + timedelta(minutes=30), inicio_nuevo=None, fin_nuevo=None,
        ocurrido_en=INICIO - timedelta(days=2),
    )


def _reprogramado() -> EventoTurno:
    nuevo = INICIO + timedelta(days=2)
    return EventoTurno(
        tipo="turno_reprogramado", turno_id=42, profesional_id=7, inicio_anterior=INICIO,
        fin_anterior=INICIO + timedelta(minutes=30), inicio_nuevo=nuevo,
        fin_nuevo=nuevo + timedelta(minutes=30), ocurrido_en=INICIO - timedelta(days=3),
    )


@pytest.mark.parametrize("evento", [_cancelado(), _reprogramado()])
def test_el_evento_no_tiene_campos_de_contacto(evento: EventoTurno) -> None:
    campos = {f.name for f in dataclasses.fields(evento)}
    assert not [c for c in campos if any(p in c for p in PROHIBIDOS)]
    assert {"tipo", "turno_id", "profesional_id", "inicio_anterior", "fin_anterior"} <= campos


def test_el_evento_es_inmutable() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        _cancelado().turno_id = 99  # type: ignore[misc]


def test_cancelacion_no_lleva_horario_nuevo_y_reprogramacion_si() -> None:
    assert _cancelado().inicio_nuevo is None
    r = _reprogramado()
    assert r.inicio_nuevo is not None and r.fin_nuevo is not None and r.inicio_nuevo > r.inicio_anterior


@pytest.mark.parametrize("evento", [_cancelado(), _reprogramado()])
async def test_notificador_nulo_loguea_tipo_y_turno_sin_pii(
    evento: EventoTurno, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        await NotificadorNulo().publicar(evento)
    texto = " ".join(r.getMessage() for r in caplog.records)
    assert evento.tipo in texto
    assert f"turno_id={evento.turno_id}" in texto
    assert "Carlos" not in texto and "+54" not in texto
