"""C-06 (3.4 + hallazgo 1): configuración de Mercado Pago por variables de entorno (R17). Falla cerrado."""

import pytest
from pydantic import ValidationError

from app.shared.settings import Settings

BASE = {"JWT_SECRET_KEY": "x" * 40}
SECRETO_MP = "TOKEN-SINTETICO-QUE-NO-DEBE-FILTRARSE"


def _settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    for clave in ("MP_GATEWAY", "MP_ACCESS_TOKEN", "MP_WEBHOOK_SECRET", "APP_ENV"):
        monkeypatch.delenv(clave, raising=False)
    for clave, valor in {**BASE, **env}.items():
        monkeypatch.setenv(clave, valor)
    return Settings(_env_file=None)  # type: ignore[call-arg]


def test_sin_variables_los_defaults_son_los_seguros_y_exigen_credenciales(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail-safe: sin APP_ENV ni MP_GATEWAY es producción con Mercado Pago real, así que faltan las credenciales."""
    with pytest.raises(ValidationError) as exc:
        _settings(monkeypatch)
    assert "MP_ACCESS_TOKEN" in str(exc.value)


@pytest.mark.parametrize("entorno", ["test", "e2e"])
def test_la_pasarela_falsa_solo_se_permite_en_test_y_e2e(monkeypatch: pytest.MonkeyPatch, entorno: str) -> None:
    s = _settings(monkeypatch, APP_ENV=entorno, MP_GATEWAY="fake")
    assert s.mp_gateway == "fake" and s.app_env == entorno
    assert s.sena_barrido_segundos == 60 and s.mp_webhook_tolerancia_segundos == 300


@pytest.mark.parametrize("entorno", ["development", "production"])
def test_la_pasarela_falsa_fuera_de_test_y_e2e_no_arranca(monkeypatch: pytest.MonkeyPatch, entorno: str) -> None:
    """Con la falsa se podría forjar un pago: un webhook firmado con un secreto conocido acreditaría sin pagar."""
    with pytest.raises(ValidationError) as exc:
        _settings(monkeypatch, APP_ENV=entorno, MP_GATEWAY="fake", MP_WEBHOOK_SECRET="secreto-de-un-repositorio")
    assert "MP_GATEWAY" in str(exc.value)


def test_pasarela_falsa_con_el_entorno_por_defecto_no_arranca(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError):
        _settings(monkeypatch, MP_GATEWAY="fake")


@pytest.mark.parametrize("faltante,presente", [
    ("MP_ACCESS_TOKEN", {"MP_WEBHOOK_SECRET": SECRETO_MP}),
    ("MP_WEBHOOK_SECRET", {"MP_ACCESS_TOKEN": SECRETO_MP}),
])
def test_mercadopago_sin_credenciales_falla_nombrando_la_variable(
        monkeypatch: pytest.MonkeyPatch, faltante: str, presente: dict[str, str]) -> None:
    with pytest.raises(ValidationError) as exc:
        _settings(monkeypatch, MP_GATEWAY="mercadopago", **presente)
    mensaje = str(exc.value)
    assert faltante in mensaje
    assert SECRETO_MP not in mensaje


def test_mercadopago_con_credenciales_vale_y_no_las_muestra(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch, MP_GATEWAY="mercadopago", MP_ACCESS_TOKEN=SECRETO_MP, MP_WEBHOOK_SECRET="otro-secreto")
    assert s.mp_access_token is not None and s.mp_access_token.get_secret_value() == SECRETO_MP
    assert SECRETO_MP not in repr(s) and SECRETO_MP not in str(s)
    assert s.app_env == "production"  # el default es el seguro


def test_produccion_con_mercadopago_es_valida(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch, APP_ENV="production", MP_GATEWAY="mercadopago",
                  MP_ACCESS_TOKEN=SECRETO_MP, MP_WEBHOOK_SECRET="otro-secreto")
    assert s.app_env == "production"


def test_mercadopago_real_tambien_es_valido_en_desarrollo(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch, APP_ENV="development", MP_GATEWAY="mercadopago",
                  MP_ACCESS_TOKEN=SECRETO_MP, MP_WEBHOOK_SECRET="otro-secreto")
    assert s.mp_gateway == "mercadopago"
