"""C-10 (3.1-3.2): contenido del evento, id determinista y hash (funciones puras, sin base). Sintético (R19)."""

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.integraciones.gcal.contenido import armar_contenido, hash_contenido, id_evento

BA = ZoneInfo("America/Argentina/Buenos_Aires")
PANEL = "http://localhost:5174"
INICIO = datetime(2031, 11, 17, 13, 0, tzinfo=timezone.utc)  # 10:00 en la clínica
FIN = datetime(2031, 11, 17, 13, 30, tzinfo=timezone.utc)


def _contenido(tratamiento: str = "Limpieza", sillon: str = "Sillón 2", inicio: datetime = INICIO,
               fin: datetime = FIN, turno_id: int = 508):
    return armar_contenido(turno_id=turno_id, tratamiento=tratamiento, sillon=sillon, inicio=inicio, fin=fin,
                           zona=BA, url_panel=PANEL)


def test_el_titulo_y_la_descripcion_no_identifican_al_paciente() -> None:
    c = _contenido()
    assert c.titulo == "Turno · Limpieza"
    assert "Sillón 2" in c.descripcion and f"{PANEL}/#/agenda?fecha=2031-11-17" in c.descripcion
    todo = " ".join([c.titulo, c.descripcion, *c.propiedades_privadas.values()])
    for dato in ("Paciente Ficticio", "+5491100000000", "codigo", "DNI"):
        assert dato not in todo


def test_el_horario_sale_en_la_hora_de_la_clinica_con_su_zona() -> None:
    c = _contenido()
    assert c.inicio.utcoffset() is not None and c.inicio.hour == 10 and c.fin.hour == 10 and c.fin.minute == 30
    assert c.zona == "America/Argentina/Buenos_Aires"


def test_se_marca_como_evento_del_sistema() -> None:
    assert _contenido().propiedades_privadas == {"turnos_sistema": "1", "turno_id": "508"}


def test_otro_tratamiento_otro_sillon_y_cruce_de_medianoche_utc() -> None:
    c = _contenido("Endodoncia", "Sillón 1", datetime(2031, 11, 18, 2, 30, tzinfo=timezone.utc),
                   datetime(2031, 11, 18, 3, 30, tzinfo=timezone.utc))
    assert c.titulo == "Turno · Endodoncia" and "Sillón 1" in c.descripcion
    assert c.inicio.day == 17 and "fecha=2031-11-17" in c.descripcion  # 23:30 local del día anterior


def test_el_id_es_base32hex_valido_para_google_y_determinista() -> None:
    a = id_evento(508, 3, 0)
    assert a == id_evento(508, 3, 0)
    assert re.fullmatch(r"[a-v0-9]{5,1024}", a)
    assert len({a, id_evento(508, 3, 1), id_evento(509, 3, 0), id_evento(508, 4, 0)}) == 4


def test_el_hash_es_estable_y_cambia_con_horario_o_titulo() -> None:
    base = hash_contenido(_contenido())
    assert base == hash_contenido(_contenido())
    assert base != hash_contenido(_contenido(tratamiento="Limpieza dental"))
    assert base != hash_contenido(_contenido(inicio=INICIO.replace(hour=14), fin=FIN.replace(hour=14)))
    assert base != hash_contenido(_contenido(sillon="Sillón 3"))
