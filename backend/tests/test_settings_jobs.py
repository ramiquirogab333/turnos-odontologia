"""C-09 (1.2, D8): configuración del worker, los recordatorios y WhatsApp por entorno (R17)."""

from datetime import timedelta

import pytest
from pydantic import ValidationError

from app.shared.settings import Settings

BASE = {"JWT_SECRET_KEY": "x" * 40, "APP_ENV": "test", "MP_GATEWAY": "fake"}
VARIABLES = ("REDIS_URL", "REMINDER_LEAD_TIME", "RECORDATORIOS_INTERVALO_SEGUNDOS", "RECORDATORIOS_HABILITADO",
             "WHATSAPP_PROVEEDOR", "CLINICA_NOMBRE", "SENA_BARRIDO_EN_API")


def _settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    for variable in VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    for clave, valor in {**BASE, **env}.items():
        monkeypatch.setenv(clave, valor)
    return Settings(_env_file=None)  # type: ignore[call-arg]


def test_los_valores_por_defecto(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch)
    assert s.redis_url == "redis://localhost:6379/0"
    assert s.reminder_lead_time == 48
    assert s.anticipacion_recordatorio == timedelta(hours=48)
    assert s.recordatorios_intervalo_segundos == 300
    assert s.recordatorios_habilitado is True
    assert s.whatsapp_proveedor == "manual"
    assert s.clinica_nombre == "la clínica"
    assert s.sena_barrido_en_api is False


@pytest.mark.parametrize("valor,horas", [("48", 48), ("48h", 48), ("24", 24), ("72H", 72)])
def test_la_anticipacion_acepta_horas_con_o_sin_sufijo(monkeypatch: pytest.MonkeyPatch, valor: str, horas: int) -> None:
    s = _settings(monkeypatch, REMINDER_LEAD_TIME=valor)
    assert s.reminder_lead_time == horas
    assert s.anticipacion_recordatorio == timedelta(hours=horas)


@pytest.mark.parametrize("valor", ["0", "abc", "-5", "0h"])
def test_una_anticipacion_invalida_no_arranca_y_nombra_la_variable(monkeypatch: pytest.MonkeyPatch, valor: str) -> None:
    with pytest.raises(ValidationError) as exc:
        _settings(monkeypatch, REMINDER_LEAD_TIME=valor)
    assert "reminder_lead_time" in str(exc.value).lower()


@pytest.mark.parametrize("valor", ["0", "-1", "abc"])
def test_un_intervalo_invalido_no_arranca_y_no_muestra_el_valor_de_secretos(monkeypatch: pytest.MonkeyPatch,
                                                                            valor: str) -> None:
    with pytest.raises(ValidationError) as exc:
        _settings(monkeypatch, RECORDATORIOS_INTERVALO_SEGUNDOS=valor)
    mensaje = str(exc.value)
    assert "recordatorios_intervalo_segundos" in mensaje.lower()
    assert "x" * 40 not in mensaje


def test_un_intervalo_corto_para_e2e_es_valido(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _settings(monkeypatch, RECORDATORIOS_INTERVALO_SEGUNDOS="3").recordatorios_intervalo_segundos == 3


def test_las_banderas_y_el_nombre_se_leen_del_entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch, RECORDATORIOS_HABILITADO="false", SENA_BARRIDO_EN_API="true",
                  CLINICA_NOMBRE="Consultorio Ficticio", REDIS_URL="redis://redis:6379/1")
    assert s.recordatorios_habilitado is False
    assert s.sena_barrido_en_api is True
    assert s.clinica_nombre == "Consultorio Ficticio"
    assert s.redis_url == "redis://redis:6379/1"


def test_el_proveedor_falso_solo_existe_en_test(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _settings(monkeypatch, WHATSAPP_PROVEEDOR="falso").whatsapp_proveedor == "falso"
    with pytest.raises(ValidationError) as exc:
        _settings(monkeypatch, WHATSAPP_PROVEEDOR="falso", APP_ENV="e2e")
    assert "WHATSAPP_PROVEEDOR" in str(exc.value)


def test_un_proveedor_desconocido_no_arranca(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError):
        _settings(monkeypatch, WHATSAPP_PROVEEDOR="twilio")
