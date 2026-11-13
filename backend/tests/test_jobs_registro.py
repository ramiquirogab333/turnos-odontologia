"""C-09 (5.1, D1): registro de trabajos periódicos y adaptador que no deja caer al worker. Sin Redis."""

import logging
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.jobs.registro import TrabajoProgramado, ejecutar_trabajo, trabajos_programados
from app.jobs.worker import construir_cron, especificacion_cron
from app.shared.settings import Settings

BASE = {"JWT_SECRET_KEY": "x" * 40, "APP_ENV": "test", "MP_GATEWAY": "fake"}
VARIABLES = ("RECORDATORIOS_HABILITADO", "RECORDATORIOS_INTERVALO_SEGUNDOS", "SENA_BARRIDO_HABILITADO",
             "SENA_BARRIDO_SEGUNDOS", "PURGA_SESIONES_HABILITADO", "PURGA_SESIONES_INTERVALO_SEGUNDOS")


def _settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    for variable in VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    for clave, valor in {**BASE, **env}.items():
        monkeypatch.setenv(clave, valor)
    return Settings(_env_file=None)  # type: ignore[call-arg]


def test_el_registro_expone_recordatorios_y_barrido_con_sus_intervalos(monkeypatch: pytest.MonkeyPatch) -> None:
    trabajos = {t.nombre: t.intervalo_segundos for t in trabajos_programados(_settings(monkeypatch))}
    assert trabajos == {"recordatorios": 300, "barrido_sena": 60, "purga_sesiones": 3600}


def test_los_intervalos_salen_de_la_configuracion(monkeypatch: pytest.MonkeyPatch) -> None:
    ajustes = _settings(monkeypatch, RECORDATORIOS_INTERVALO_SEGUNDOS="3", SENA_BARRIDO_SEGUNDOS="3")
    assert {t.nombre: t.intervalo_segundos for t in trabajos_programados(ajustes)} == {
        "recordatorios": 3, "barrido_sena": 3, "purga_sesiones": 3600}


def test_la_purga_de_sesiones_se_registra_con_su_intervalo_y_se_puede_apagar(monkeypatch: pytest.MonkeyPatch) -> None:
    ajustes = _settings(monkeypatch, PURGA_SESIONES_INTERVALO_SEGUNDOS="120")
    assert {t.nombre: t.intervalo_segundos for t in trabajos_programados(ajustes)}["purga_sesiones"] == 120
    apagada = _settings(monkeypatch, PURGA_SESIONES_HABILITADO="false")
    assert "purga_sesiones" not in {t.nombre for t in trabajos_programados(apagada)}


@pytest.mark.parametrize("variable,omitido", [("RECORDATORIOS_HABILITADO", "recordatorios"),
                                              ("SENA_BARRIDO_HABILITADO", "barrido_sena")])
def test_un_trabajo_con_su_bandera_apagada_se_omite(monkeypatch: pytest.MonkeyPatch, variable: str,
                                                    omitido: str) -> None:
    nombres = {t.nombre for t in trabajos_programados(_settings(monkeypatch, **{variable: "false"}))}
    assert omitido not in nombres and nombres == {"recordatorios", "barrido_sena", "purga_sesiones"} - {omitido}


def test_con_ambas_banderas_apagadas_no_hay_trabajos(monkeypatch: pytest.MonkeyPatch) -> None:
    ajustes = _settings(monkeypatch, RECORDATORIOS_HABILITADO="false", SENA_BARRIDO_HABILITADO="false",
                        PURGA_SESIONES_HABILITADO="false")
    assert trabajos_programados(ajustes) == []


@pytest.mark.parametrize("intervalo,esperado", [
    (3, {"second": set(range(0, 60, 3))}),
    (60, {"minute": set(range(60)), "second": 0}),
    (300, {"minute": set(range(0, 60, 5)), "second": 0}),
    (7, {"second": set(range(0, 60, 6))}),  # sin divisor exacto: se baja al divisor de 60 más cercano
    (90, {"minute": set(range(60)), "second": 0}),
    (3600, {"hour": set(range(24)), "minute": 0, "second": 0}),
])
def test_el_intervalo_se_traduce_a_una_expresion_cron(intervalo: int, esperado: dict[str, object]) -> None:
    assert especificacion_cron(intervalo) == esperado


def test_se_arma_un_cron_por_trabajo_con_su_nombre(monkeypatch: pytest.MonkeyPatch) -> None:
    crones = construir_cron(trabajos_programados(_settings(monkeypatch)))
    assert sorted(c.name for c in crones) == ["barrido_sena", "purga_sesiones", "recordatorios"]


async def test_el_adaptador_abre_la_sesion_y_pasa_ahora_con_zona(
        session_factory: async_sessionmaker[AsyncSession]) -> None:
    recibido: dict[str, object] = {}

    async def funcion(session: AsyncSession, ahora: datetime) -> int:
        recibido["sesion"] = isinstance(session, AsyncSession)
        recibido["ahora"] = ahora
        return 7

    resultado = await ejecutar_trabajo(TrabajoProgramado("falso", 5, funcion), session_factory)
    assert resultado == 7 and recibido["sesion"] is True
    ahora = recibido["ahora"]
    assert isinstance(ahora, datetime) and ahora.tzinfo is not None and ahora.utcoffset() is not None


async def test_una_excepcion_del_trabajo_se_loguea_sin_datos_personales_y_no_se_propaga(
        session_factory: async_sessionmaker[AsyncSession], caplog: pytest.LogCaptureFixture) -> None:
    async def funcion(session: AsyncSession, ahora: datetime) -> int:
        raise RuntimeError("falló para +5491100000003 Carlos Sintético")

    with caplog.at_level(logging.DEBUG):
        resultado = await ejecutar_trabajo(TrabajoProgramado("roto", 5, funcion), session_factory)
    assert resultado is None
    assert "roto" in caplog.text and "RuntimeError" in caplog.text
    assert "5491100000003" not in caplog.text and "Carlos" not in caplog.text


async def test_tras_un_error_el_mismo_trabajo_corre_en_el_siguiente_ciclo(
        session_factory: async_sessionmaker[AsyncSession]) -> None:
    llamadas = {"n": 0}

    async def funcion(session: AsyncSession, ahora: datetime) -> int:
        llamadas["n"] += 1
        if llamadas["n"] == 1:
            raise ConnectionError("base caída")
        return 1

    trabajo = TrabajoProgramado("intermitente", 5, funcion)
    assert await ejecutar_trabajo(trabajo, session_factory) is None
    assert await ejecutar_trabajo(trabajo, session_factory) == 1


# --- 5.4 Idempotencia ante ejecuciones concurrentes ---------------------------------------------------------------

async def test_dos_barridos_concurrentes_cancelan_una_vez_y_dejan_una_sola_auditoria(
        session_factory: async_sessionmaker[AsyncSession]) -> None:
    import asyncio
    from datetime import timedelta

    from sqlalchemy import select

    from app.models.core import RegistroAuditoria
    from app.pagos.barrido import expirar_pre_reservas
    from tests.panel_helpers import insertar_pago, insertar_turno, pagos, sembrar_mundo, turno

    mundo = await sembrar_mundo(session_factory)
    ahora = datetime.now(tz=timezone.utc)
    vencido = await insertar_turno(session_factory, mundo, ahora + timedelta(days=3), estado="en_espera",
                                   vence=ahora - timedelta(minutes=1))
    await insertar_pago(session_factory, vencido, "pendiente")

    async def barrer() -> int:
        async with session_factory() as s:
            return await expirar_pre_reservas(s, ahora)

    resultados = await asyncio.gather(barrer(), barrer(), barrer())
    assert sorted(resultados) == [0, 0, 1]
    assert (await turno(session_factory, vencido)).estado == "cancelado"
    assert [p.estado for p in await pagos(session_factory, vencido)] == ["vencido"]
    async with session_factory() as s:
        auditorias = (await s.execute(select(RegistroAuditoria).where(
            RegistroAuditoria.entidad == "turno", RegistroAuditoria.entidad_id == str(vencido)))).scalars().all()
    assert len(auditorias) == 1 and auditorias[0].datos_despues["origen"] == "vencimiento_sena"
