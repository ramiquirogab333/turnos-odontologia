"""C-09 (3.1-3.2, D4): mensaje y link ``wa.me`` del recordatorio. Funciones puras, sin base. Datos sintéticos (R19)."""

from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import pytest

from app.notificaciones.mensaje import DatosMensaje, armar_mensaje, link_wa_me

BA = ZoneInfo("America/Argentina/Buenos_Aires")
BASE = "https://turnos.ficticia.test"
# Martes 17/11/2026 a las 10:30 en la clínica = 13:30 UTC.
INICIO = datetime(2026, 11, 17, 13, 30, tzinfo=timezone.utc)


def _datos(**cambios: object) -> DatosMensaje:
    base = dict(nombre="Carlos Sintético", inicio=INICIO, profesional="Dra. Ficticia", tratamiento="Limpieza",
                codigo_gestion="CODIGO-SINTETICO-114")
    base.update(cambios)
    return DatosMensaje(**base)  # type: ignore[arg-type]


def _texto(link: str) -> str:
    return parse_qs(urlsplit(link).query)["text"][0]


def test_el_link_lleva_el_telefono_sin_mas_y_el_mensaje_con_todos_los_datos() -> None:
    texto = armar_mensaje(_datos(), BA, BASE, "Consultorio Ficticio")
    link = link_wa_me("+5491100000001", texto)
    assert link.startswith("https://wa.me/5491100000001?text=")
    decodificado = _texto(link)
    for fragmento in ("Carlos Sintético", "martes 17/11", "10:30", "Dra. Ficticia", "Limpieza", "Consultorio Ficticio",
                      f"{BASE}/confirmar#CODIGO-SINTETICO-114", f"{BASE}/gestionar#CODIGO-SINTETICO-114"):
        assert fragmento in decodificado, fragmento


def test_otra_profesional_otra_clinica_y_otro_dia() -> None:
    sabado = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)  # sábado 09:00 en la clínica
    texto = armar_mensaje(_datos(nombre="Lucía Ficticia", inicio=sabado, profesional="Dr. Bruno Ejemplo",
                                 tratamiento="Ortodoncia", codigo_gestion="CODIGO-SINTETICO-200"), BA, BASE,
                          "Clínica Dental Ejemplo")
    assert "Lucía Ficticia" in texto and "sábado 21/11" in texto and "09:00" in texto
    assert "Dr. Bruno Ejemplo" in texto and "Ortodoncia" in texto and "Clínica Dental Ejemplo" in texto
    assert "Carlos" not in texto and "Consultorio Ficticio" not in texto


def test_el_cambio_de_dia_en_utc_se_muestra_en_hora_de_la_clinica() -> None:
    inicio = datetime(2026, 11, 18, 0, 30, tzinfo=timezone.utc)  # 17/11 21:30 en la clínica
    texto = armar_mensaje(_datos(inicio=inicio), BA, BASE, "Consultorio Ficticio")
    assert "17/11" in texto and "21:30" in texto
    assert "18/11" not in texto and "00:30" not in texto


def test_los_caracteres_especiales_quedan_codificados_en_la_url() -> None:
    link = link_wa_me("+5491100000001", "¿Venís? Sí & más #1")
    consulta = urlsplit(link).query
    for crudo in ("¿", "í", " ", "&", "#"):
        assert crudo not in consulta, crudo
    assert "%C2%BF" in consulta and "%26" in consulta and "%23" in consulta
    assert _texto(link) == "¿Venís? Sí & más #1"
    assert "#" not in link


def test_el_codigo_solo_aparece_en_el_fragmento_despues_de_la_almohadilla() -> None:
    texto = armar_mensaje(_datos(), BA, BASE, "Consultorio Ficticio")
    assert texto.count("CODIGO-SINTETICO-114") == 2
    assert texto.count("#CODIGO-SINTETICO-114") == 2
    assert "?codigo" not in texto and "codigo=" not in texto


def test_un_turno_interno_sin_codigo_no_lleva_enlaces_y_pide_responder() -> None:
    texto = armar_mensaje(_datos(codigo_gestion=None), BA, BASE, "Consultorio Ficticio")
    assert "/confirmar#" not in texto and "/gestionar#" not in texto and "http" not in texto
    assert "respond" in texto.lower()


def test_sin_nombre_de_contacto_saluda_sin_nombre() -> None:
    texto = armar_mensaje(_datos(nombre=None), BA, BASE, "Consultorio Ficticio")
    assert texto.startswith("Hola")
    assert "None" not in texto and "Hola ," not in texto


def test_la_base_con_barra_final_no_duplica_barras() -> None:
    texto = armar_mensaje(_datos(), BA, BASE + "/", "Consultorio Ficticio")
    assert f"{BASE}/confirmar#" in texto and "//confirmar" not in texto


@pytest.mark.parametrize("telefono", ["5491100000001", "1100000001", "+0123"])
def test_un_telefono_que_no_es_e164_se_rechaza(telefono: str) -> None:
    with pytest.raises(ValueError):
        link_wa_me(telefono, "hola")
