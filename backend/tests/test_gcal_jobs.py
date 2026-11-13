"""C-10 (9.3): el registro de trabajos suma ``gcal_sync`` solo con credenciales y bandera. Sin Redis ni red."""

import logging
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.jobs.registro import trabajos_programados
from app.jobs.worker import construir_cron
from app.integraciones.gcal.proveedor_falso import ProveedorFalso
from app.shared.settings import Settings
from tests.gcal_helpers import AHORA, CLAVE_FERNET, eventos, sembrar_conexion
from tests.panel_helpers import insertar_turno, sembrar_mundo

BASE = {"JWT_SECRET_KEY": "x" * 40, "APP_ENV": "test", "MP_GATEWAY": "fake", "GCAL_CLIENT_ID": "cliente-sintetico",
        "GCAL_CLIENT_SECRET": "secreto-sintetico", "GCAL_TOKEN_CLAVE": CLAVE_FERNET}
VARIABLES = ("GCAL_CLIENT_ID", "GCAL_CLIENT_SECRET", "GCAL_TOKEN_CLAVE", "GCAL_SYNC_HABILITADO",
             "GCAL_SYNC_INTERVALO_SEGUNDOS", "RECORDATORIOS_HABILITADO", "SENA_BARRIDO_HABILITADO")


def _settings(monkeypatch: pytest.MonkeyPatch, quitar: tuple[str, ...] = (), **env: str) -> Settings:
    for variable in VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    for clave, valor in {**BASE, **env}.items():
        if clave not in quitar:
            monkeypatch.setenv(clave, valor)
    return Settings(_env_file=None)  # type: ignore[call-arg]


def _intervalos(ajustes: Settings) -> dict[str, int]:
    return {t.nombre: t.intervalo_segundos for t in trabajos_programados(ajustes, ProveedorFalso())}


def test_el_trabajo_gcal_sync_se_registra_con_su_intervalo_junto_a_los_otros(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _intervalos(_settings(monkeypatch)) == {"recordatorios": 300, "barrido_sena": 60, "gcal_sync": 60}


def test_el_intervalo_corto_para_e2e_llega_al_cron(monkeypatch: pytest.MonkeyPatch) -> None:
    ajustes = _settings(monkeypatch, GCAL_SYNC_INTERVALO_SEGUNDOS="3")
    assert _intervalos(ajustes)["gcal_sync"] == 3
    crones = {c.name: c for c in construir_cron(trabajos_programados(ajustes, ProveedorFalso()))}
    assert "gcal_sync" in crones


def test_sin_el_secreto_no_se_registra_avisa_sin_mostrarlo_y_los_otros_corren(
        monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    ajustes = _settings(monkeypatch, quitar=("GCAL_CLIENT_SECRET",))
    assert _intervalos(ajustes) == {"recordatorios": 300, "barrido_sena": 60}
    assert "gcal_sync" in caplog.text and "secreto-sintetico" not in caplog.text and CLAVE_FERNET not in caplog.text


def test_con_la_bandera_apagada_no_se_registra(monkeypatch: pytest.MonkeyPatch) -> None:
    assert "gcal_sync" not in _intervalos(_settings(monkeypatch, GCAL_SYNC_HABILITADO="false"))


async def test_el_trabajo_corre_un_ciclo_completo_con_la_sesion_que_recibe(
        monkeypatch: pytest.MonkeyPatch, session_factory: async_sessionmaker[AsyncSession]) -> None:
    ajustes = _settings(monkeypatch)
    mundo = await sembrar_mundo(session_factory)
    conexion = await sembrar_conexion(session_factory, mundo["ana"])
    await insertar_turno(session_factory, mundo, AHORA + timedelta(days=1))
    falso = ProveedorFalso()
    [trabajo] = [t for t in trabajos_programados(ajustes, falso) if t.nombre == "gcal_sync"]
    async with session_factory() as session:
        assert await trabajo.funcion(session, AHORA) == 1
    assert len(falso.vigentes()) == 1 and len(await eventos(session_factory, conexion)) == 1
