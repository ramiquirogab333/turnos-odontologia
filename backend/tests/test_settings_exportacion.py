"""C-13 (1.1, D10, O15): límites de exportación por entorno (R17)."""

import pytest
from pydantic import ValidationError

from app.shared.settings import Settings

BASE = {"JWT_SECRET_KEY": "x" * 40, "APP_ENV": "test", "MP_GATEWAY": "fake"}


def _settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    monkeypatch.delenv("EXPORT_MAX_POR_HORA", raising=False)
    monkeypatch.delenv("EXPORT_TIMEOUT_SEGUNDOS", raising=False)
    for clave, valor in {**BASE, **env}.items():
        monkeypatch.setenv(clave, valor)
    return Settings(_env_file=None)  # type: ignore[call-arg]


def test_los_defaults_son_veinte_por_hora_y_trescientos_segundos(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _settings(monkeypatch)
    assert (cfg.export_max_por_hora, cfg.export_timeout_segundos) == (20, 300)


@pytest.mark.parametrize("valor,esperado", [("1", 1), ("1000", 1000)])
def test_los_valores_se_leen_del_entorno(monkeypatch: pytest.MonkeyPatch, valor: str, esperado: int) -> None:
    cfg = _settings(monkeypatch, EXPORT_MAX_POR_HORA=valor, EXPORT_TIMEOUT_SEGUNDOS=valor)
    assert (cfg.export_max_por_hora, cfg.export_timeout_segundos) == (esperado, esperado)


@pytest.mark.parametrize("variable", ["EXPORT_MAX_POR_HORA", "EXPORT_TIMEOUT_SEGUNDOS"])
@pytest.mark.parametrize("valor", ["0", "-1", "abc"])
def test_un_valor_invalido_no_arranca_y_nombra_la_variable(
        monkeypatch: pytest.MonkeyPatch, variable: str, valor: str) -> None:
    with pytest.raises(ValidationError) as exc:
        _settings(monkeypatch, **{variable: valor})
    assert variable in str(exc.value).upper()
