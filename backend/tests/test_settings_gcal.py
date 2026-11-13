"""C-10 (1.2): configuración de Google Calendar (D10, O1). Sin secretos reales (R17, R19)."""

import pytest
from cryptography.fernet import Fernet

from app.shared.settings import Settings

BASE = {"JWT_SECRET_KEY": "x" * 40, "APP_ENV": "test", "MP_GATEWAY": "fake"}
VARIABLES = ("GCAL_CLIENT_ID", "GCAL_CLIENT_SECRET", "GCAL_REDIRECT_URI", "GCAL_TOKEN_CLAVE", "GCAL_SYNC_HABILITADO",
             "GCAL_SYNC_INTERVALO_SEGUNDOS", "GCAL_HORIZONTE_DIAS", "PUBLIC_PANEL_URL", "GCAL_OAUTH_BASE_URL",
             "GCAL_API_BASE_URL", "GCAL_TOKEN_BASE_URL")
CLAVE = Fernet.generate_key().decode()


def _settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    for variable in VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    for clave, valor in {**BASE, **env}.items():
        monkeypatch.setenv(clave, valor)
    return Settings(_env_file=None)  # type: ignore[call-arg]


def test_los_valores_por_defecto_son_seguros(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch)
    assert (s.gcal_sync_habilitado, s.gcal_sync_intervalo_segundos, s.gcal_horizonte_dias) == (True, 60, 60)
    assert s.gcal_configurado is False and s.gcal_client_id is None


def test_con_credenciales_completas_queda_configurado(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch, GCAL_CLIENT_ID="cliente-sintetico", GCAL_CLIENT_SECRET="secreto-sintetico",
                  GCAL_TOKEN_CLAVE=CLAVE)
    assert s.gcal_configurado is True
    assert s.gcal_client_secret is not None and "secreto-sintetico" not in repr(s.gcal_client_secret)


def test_sin_secreto_no_esta_configurado_pero_arranca(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch, GCAL_CLIENT_ID="cliente-sintetico", GCAL_TOKEN_CLAVE=CLAVE)
    assert s.gcal_configurado is False


def test_la_clave_de_cifrado_es_obligatoria_con_client_id(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="GCAL_TOKEN_CLAVE"):
        _settings(monkeypatch, GCAL_CLIENT_ID="cliente-sintetico", GCAL_CLIENT_SECRET="secreto-sintetico")


def test_una_clave_fernet_invalida_se_rechaza_sin_mostrarla(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError) as error:
        _settings(monkeypatch, GCAL_CLIENT_ID="c", GCAL_CLIENT_SECRET="s", GCAL_TOKEN_CLAVE="clave-invalida-123")
    assert "clave-invalida-123" not in str(error.value) and "Fernet" in str(error.value)


@pytest.mark.parametrize("valor", ["0", "-5", "abc"])
def test_el_intervalo_rechaza_valores_invalidos(monkeypatch: pytest.MonkeyPatch, valor: str) -> None:
    with pytest.raises(ValueError):
        _settings(monkeypatch, GCAL_SYNC_INTERVALO_SEGUNDOS=valor)


@pytest.mark.parametrize("valor,ok", [("1", True), ("365", True), ("0", False), ("366", False)])
def test_el_horizonte_esta_entre_1_y_365(monkeypatch: pytest.MonkeyPatch, valor: str, ok: bool) -> None:
    if ok:
        assert _settings(monkeypatch, GCAL_HORIZONTE_DIAS=valor).gcal_horizonte_dias == int(valor)
    else:
        with pytest.raises(ValueError):
            _settings(monkeypatch, GCAL_HORIZONTE_DIAS=valor)


@pytest.mark.parametrize("variable", ["GCAL_API_BASE_URL", "GCAL_OAUTH_BASE_URL", "GCAL_TOKEN_BASE_URL"])
def test_cada_url_base_se_lee_de_su_variable_con_default_de_google(monkeypatch: pytest.MonkeyPatch, variable: str) -> None:
    por_defecto = _settings(monkeypatch)
    assert "google" in f"{por_defecto.gcal_api_base_url}{por_defecto.gcal_oauth_base_url}{por_defecto.gcal_token_base_url}"
    campo = variable.lower()
    assert _settings(monkeypatch, **{variable: "http://gcal-falso:8090"}).__getattribute__(campo) == "http://gcal-falso:8090"


@pytest.mark.parametrize("entorno,ok", [("test", True), ("e2e", True), ("production", False), ("development", False)])
def test_las_urls_distintas_de_google_solo_en_test_o_e2e(monkeypatch: pytest.MonkeyPatch, entorno: str,
                                                          ok: bool) -> None:
    env = {"APP_ENV": entorno, "GCAL_API_BASE_URL": "http://gcal-falso:8090"}
    if entorno in ("production", "development"):
        env.update(MP_GATEWAY="mercadopago", MP_ACCESS_TOKEN="t", MP_WEBHOOK_SECRET="w")
    if ok:
        assert _settings(monkeypatch, **env).gcal_api_base_url == "http://gcal-falso:8090"
    else:
        with pytest.raises(ValueError, match="GCAL_"):
            _settings(monkeypatch, **env)
