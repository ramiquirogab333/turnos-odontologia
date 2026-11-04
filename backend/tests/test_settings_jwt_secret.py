"""Settings must reject missing or short JWT secrets (R17; auth is CRITICAL)."""

import pytest
from pydantic import ValidationError

from app.shared.settings import Settings

# Valores sintéticos (R19): ninguno es un secreto real.
SECRET_31 = "a" * 31
SECRET_32 = "b" * 32


def _build(monkeypatch: pytest.MonkeyPatch, secret: str | None) -> Settings:
    """Build Settings from the environment only, ignoring any local .env file."""
    if secret is None:
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    else:
        monkeypatch.setenv("JWT_SECRET_KEY", secret)
    return Settings(_env_file=None)


def test_rejects_unset_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError):
        _build(monkeypatch, None)


def test_rejects_empty_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError):
        _build(monkeypatch, "")


def test_rejects_31_char_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError) as excinfo:
        _build(monkeypatch, SECRET_31)
    assert "32" in str(excinfo.value)


def test_accepts_exactly_32_char_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _build(monkeypatch, SECRET_32)
    assert settings.jwt_secret_key == SECRET_32


def test_accepts_longer_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _build(monkeypatch, "c" * 64).jwt_secret_key == "c" * 64


def test_error_does_not_leak_secret_value(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError) as excinfo:
        _build(monkeypatch, SECRET_31)
    assert SECRET_31 not in str(excinfo.value)
