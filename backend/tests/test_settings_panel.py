"""C-08 (1.3, O14): tolerancia del ausente por entorno (R17)."""

import pytest
from pydantic import ValidationError

from app.shared.settings import Settings

BASE = {"JWT_SECRET_KEY": "x" * 40, "APP_ENV": "test", "MP_GATEWAY": "fake"}


def _settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    monkeypatch.delenv("AUSENTE_TOLERANCIA_MINUTOS", raising=False)
    for clave, valor in {**BASE, **env}.items():
        monkeypatch.setenv(clave, valor)
    return Settings(_env_file=None)  # type: ignore[call-arg]


def test_la_tolerancia_por_defecto_es_diez_minutos(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _settings(monkeypatch).ausente_tolerancia_minutos == 10


@pytest.mark.parametrize("valor,esperado", [("0", 0), ("25", 25)])
def test_la_tolerancia_se_lee_de_la_variable_de_entorno(monkeypatch: pytest.MonkeyPatch, valor: str,
                                                        esperado: int) -> None:
    assert _settings(monkeypatch, AUSENTE_TOLERANCIA_MINUTOS=valor).ausente_tolerancia_minutos == esperado


@pytest.mark.parametrize("valor", ["-1", "diez"])
def test_una_tolerancia_invalida_no_arranca_y_nombra_la_variable(monkeypatch: pytest.MonkeyPatch, valor: str) -> None:
    with pytest.raises(ValidationError) as exc:
        _settings(monkeypatch, AUSENTE_TOLERANCIA_MINUTOS=valor)
    assert "AUSENTE_TOLERANCIA_MINUTOS" in str(exc.value).upper()
