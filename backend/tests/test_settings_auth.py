"""C-15 (1.1, D3/D5/D6/D8): configuración de sesión, límites, proxies y purga por entorno (R17)."""

import ipaddress

import pytest
from pydantic import ValidationError

from app.shared.settings import Settings

BASE = {"JWT_SECRET_KEY": "x" * 40, "APP_ENV": "test", "MP_GATEWAY": "fake"}
GRUPOS = ("LOGIN_IP_EMAIL", "LOGIN_IP", "LOGIN_EMAIL", "REFRESH_IP", "PUBLICO_ESCRITURA", "PUBLICO_LECTURA")
DEFAULTS = {
    "LOGIN_IP_EMAIL": (5, 900),
    "LOGIN_IP": (30, 900),
    "LOGIN_EMAIL": (20, 3600),
    "REFRESH_IP": (60, 900),
    "PUBLICO_ESCRITURA": (10, 600),
    "PUBLICO_LECTURA": (120, 60),
}
VARIABLES = (
    "SESION_MAXIMA_HORAS", "RATE_LIMIT_TIMEOUT_MS", "TRUSTED_PROXIES", "PURGA_SESIONES_HABILITADO",
    "PURGA_SESIONES_INTERVALO_SEGUNDOS", "PURGA_SESIONES_MARGEN_MINUTOS",
    *[f"RATE_LIMIT_{g}_{s}" for g in GRUPOS for s in ("MAX", "VENTANA_SEG")],
)


def _settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    for variable in VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    for clave, valor in {**BASE, **env}.items():
        monkeypatch.setenv(clave, valor)
    return Settings(_env_file=None)  # type: ignore[call-arg]


def test_los_valores_por_defecto(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch)
    assert s.sesion_maxima_horas == 12
    assert s.rate_limit_timeout_ms == 200
    assert s.trusted_proxies == []
    assert s.purga_sesiones_habilitado is True
    assert s.purga_sesiones_intervalo_segundos == 3600
    assert s.purga_sesiones_margen_minutos == 60
    for grupo, (maximo, ventana) in DEFAULTS.items():
        assert getattr(s, f"rate_limit_{grupo.lower()}_max") == maximo
        assert getattr(s, f"rate_limit_{grupo.lower()}_ventana_seg") == ventana


@pytest.mark.parametrize("valor", ["1", "12", "168"])
def test_sesion_maxima_acepta_el_rango(monkeypatch: pytest.MonkeyPatch, valor: str) -> None:
    assert _settings(monkeypatch, SESION_MAXIMA_HORAS=valor).sesion_maxima_horas == int(valor)


@pytest.mark.parametrize("valor", ["0", "169", "-1", "abc"])
def test_sesion_maxima_rechaza_fuera_de_rango_nombrando_la_variable(monkeypatch: pytest.MonkeyPatch, valor: str) -> None:
    with pytest.raises(ValidationError, match="(?i)sesion_maxima_horas"):
        _settings(monkeypatch, SESION_MAXIMA_HORAS=valor)


@pytest.mark.parametrize("grupo", GRUPOS)
@pytest.mark.parametrize("sufijo", ["MAX", "VENTANA_SEG"])
@pytest.mark.parametrize("valor", ["0", "-1", "abc"])
def test_cada_limite_rechaza_cero_negativo_y_texto(monkeypatch: pytest.MonkeyPatch, grupo: str, sufijo: str, valor: str) -> None:
    variable = f"RATE_LIMIT_{grupo}_{sufijo}"
    with pytest.raises(ValidationError, match=f"(?i){variable}"):
        _settings(monkeypatch, **{variable: valor})


def test_cada_limite_se_puede_configurar(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch, RATE_LIMIT_LOGIN_IP_MAX="1000", RATE_LIMIT_PUBLICO_LECTURA_VENTANA_SEG="30", RATE_LIMIT_TIMEOUT_MS="50")
    assert (s.rate_limit_login_ip_max, s.rate_limit_publico_lectura_ventana_seg, s.rate_limit_timeout_ms) == (1000, 30, 50)


@pytest.mark.parametrize("valor", ["0", "-5", "x"])
def test_timeout_del_limitador_debe_ser_positivo(monkeypatch: pytest.MonkeyPatch, valor: str) -> None:
    with pytest.raises(ValidationError, match="(?i)rate_limit_timeout_ms"):
        _settings(monkeypatch, RATE_LIMIT_TIMEOUT_MS=valor)


def test_trusted_proxies_acepta_ips_y_cidr_separados_por_comas(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch, TRUSTED_PROXIES="192.0.2.10, 198.51.100.0/24 ,2001:db8::1")
    assert s.trusted_proxies == ["192.0.2.10", "198.51.100.0/24", "2001:db8::1"]
    for entrada in s.trusted_proxies:
        ipaddress.ip_network(entrada)


def test_trusted_proxies_vacio_no_confia_en_nadie(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _settings(monkeypatch, TRUSTED_PROXIES="").trusted_proxies == []
    assert _settings(monkeypatch, TRUSTED_PROXIES="  ").trusted_proxies == []


@pytest.mark.parametrize("valor", ["no-es-una-ip", "192.0.2.10,basura", "192.0.2.0/99", "0.0.0.0/0", "::/0", "192.0.2.1,0.0.0.0/0"])
def test_trusted_proxies_rechaza_basura_y_redes_totales(monkeypatch: pytest.MonkeyPatch, valor: str) -> None:
    with pytest.raises(ValidationError, match="TRUSTED_PROXIES"):
        _settings(monkeypatch, TRUSTED_PROXIES=valor)


@pytest.mark.parametrize(("variable", "valor"), [
    ("PURGA_SESIONES_INTERVALO_SEGUNDOS", "0"),
    ("PURGA_SESIONES_INTERVALO_SEGUNDOS", "-1"),
    ("PURGA_SESIONES_MARGEN_MINUTOS", "-1"),
    ("PURGA_SESIONES_MARGEN_MINUTOS", "abc"),
])
def test_purga_rechaza_valores_invalidos(monkeypatch: pytest.MonkeyPatch, variable: str, valor: str) -> None:
    with pytest.raises(ValidationError, match=f"(?i){variable}"):
        _settings(monkeypatch, **{variable: valor})


def test_purga_acepta_margen_cero_y_se_puede_deshabilitar(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch, PURGA_SESIONES_MARGEN_MINUTOS="0", PURGA_SESIONES_HABILITADO="false")
    assert s.purga_sesiones_margen_minutos == 0
    assert s.purga_sesiones_habilitado is False
