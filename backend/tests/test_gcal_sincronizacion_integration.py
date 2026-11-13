"""C-10 (9.1-9.2): errores de Google sin perder cambios, backoff, token revocado y trabajo por conexión. Sintético (R19)."""

import logging
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integraciones.gcal.cifrado import cifrar
from app.integraciones.gcal.proveedor import ErrorTransitorio
from app.integraciones.gcal.proveedor_falso import ProveedorFalso
from app.integraciones.gcal.sincronizacion import LOCK_GCAL, espera_tras_fallo
from app.models.core import RegistroAuditoria
from tests.gcal_helpers import AHORA, CLAVE_FERNET, ciclo, conexion, eventos, poner_conexion, sembrar_conexion
from tests.panel_helpers import insertar_turno, sembrar_mundo

Factory = async_sessionmaker[AsyncSession]
MANANA = AHORA + timedelta(days=1)


def test_la_espera_crece_1_5_15_60_y_se_queda_en_60() -> None:
    assert [espera_tras_fallo(n) for n in (1, 2, 3, 4, 5, 9)] == [timedelta(minutes=m) for m in (1, 5, 15, 60, 60, 60)]


async def test_google_vuelve_despues_de_dos_cortes_y_el_evento_se_crea_sin_intervencion(
        session_factory: Factory, proveedor_gcal: ProveedorFalso) -> None:
    mundo = await sembrar_mundo(session_factory)
    conexion_id = await sembrar_conexion(session_factory, mundo["ana"])
    await insertar_turno(session_factory, mundo, MANANA)
    proveedor_gcal.fallar(ErrorTransitorio(503), veces=2, en=("insertar",))
    assert await ciclo(session_factory, proveedor_gcal, ahora=AHORA) == 0
    fila = await conexion(session_factory, conexion_id)
    assert (fila.fallos_consecutivos, fila.proximo_intento_en) == (1, AHORA + timedelta(minutes=1))
    llamadas = len(proveedor_gcal.llamadas)
    assert await ciclo(session_factory, proveedor_gcal, ahora=AHORA + timedelta(seconds=30)) == 0  # todavía espera
    assert len(proveedor_gcal.llamadas) == llamadas
    assert await ciclo(session_factory, proveedor_gcal, ahora=AHORA + timedelta(minutes=1)) == 0
    fila = await conexion(session_factory, conexion_id)
    assert (fila.fallos_consecutivos, fila.proximo_intento_en) == (2, AHORA + timedelta(minutes=6))
    assert fila.ultimo_error == "ErrorTransitorio 503" and proveedor_gcal.vigentes() == []
    assert await ciclo(session_factory, proveedor_gcal, ahora=AHORA + timedelta(minutes=6)) == 1
    fila = await conexion(session_factory, conexion_id)
    assert (fila.fallos_consecutivos, fila.proximo_intento_en, fila.ultimo_error) == (0, None, None)
    assert fila.ultimo_sync_ok_en == AHORA + timedelta(minutes=6) and len(proveedor_gcal.vigentes()) == 1


async def test_la_cuota_excedida_de_una_conexion_no_frena_a_las_demas_y_el_log_no_tiene_pii(
        session_factory: Factory, proveedor_gcal: ProveedorFalso, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    mundo = await sembrar_mundo(session_factory)
    primera = await sembrar_conexion(session_factory, mundo["ana"])
    segunda = await sembrar_conexion(session_factory, mundo["bruno"], calendario_id="bruno@example.com")
    await insertar_turno(session_factory, mundo, MANANA, prof="bruno", nombre="Paciente Ficticio")
    proveedor_gcal.fallar(ErrorTransitorio(429), en=("listar",))  # solo la primera llamada: la de la conexión 1
    assert await ciclo(session_factory, proveedor_gcal) == 1
    assert (await conexion(session_factory, primera)).proximo_intento_en == AHORA + timedelta(minutes=1)
    assert (await conexion(session_factory, segunda)).ultimo_sync_ok_en == AHORA
    assert len(proveedor_gcal.vigentes("bruno@example.com")) == 1
    assert "Paciente Ficticio" not in caplog.text and "token-sintetico" not in caplog.text and "429" in caplog.text


async def test_un_error_inesperado_en_una_conexion_no_corta_las_demas(
        session_factory: Factory, proveedor_gcal: ProveedorFalso, caplog: pytest.LogCaptureFixture) -> None:
    mundo = await sembrar_mundo(session_factory)
    await sembrar_conexion(session_factory, mundo["ana"])
    segunda = await sembrar_conexion(session_factory, mundo["bruno"])
    original = proveedor_gcal.listar
    llamadas = {"n": 0}

    async def listar(*args, **kwargs):  # type: ignore[no-untyped-def]
        llamadas["n"] += 1
        if llamadas["n"] == 1:
            raise RuntimeError("fallo inesperado con Paciente Ficticio")
        return await original(*args, **kwargs)

    proveedor_gcal.listar = listar  # type: ignore[method-assign]
    assert await ciclo(session_factory, proveedor_gcal) == 1
    assert (await conexion(session_factory, segunda)).ultimo_sync_ok_en == AHORA
    assert "RuntimeError" in caplog.text and "Paciente Ficticio" not in caplog.text


async def test_invalid_grant_deja_la_conexion_revocada_audita_y_no_llama_mas_a_google(
        session_factory: Factory, proveedor_gcal: ProveedorFalso) -> None:
    mundo = await sembrar_mundo(session_factory)
    conexion_id = await sembrar_conexion(session_factory, mundo["ana"],
                                         access_expira_en=AHORA - timedelta(hours=1))  # obliga a renovar
    proveedor_gcal.revocar_acceso()
    assert await ciclo(session_factory, proveedor_gcal) == 0
    assert (await conexion(session_factory, conexion_id)).estado == "revocada"
    async with session_factory() as s:
        [auditoria] = (await s.execute(select(RegistroAuditoria).where(
            RegistroAuditoria.entidad == "gcal_conexion"))).scalars().all()
    assert auditoria.usuario_id is None and auditoria.datos_despues["estado"] == "revocada"
    await insertar_turno(session_factory, mundo, MANANA)  # un turno nuevo con la conexión revocada
    llamadas = len(proveedor_gcal.llamadas)
    for _ in range(3):
        await ciclo(session_factory, proveedor_gcal)
    assert len(proveedor_gcal.llamadas) == llamadas and proveedor_gcal.vigentes() == []


async def test_reconectar_crea_los_eventos_pendientes_sin_duplicar_los_que_ya_existian(
        session_factory: Factory, proveedor_gcal: ProveedorFalso) -> None:
    mundo = await sembrar_mundo(session_factory)
    conexion_id = await sembrar_conexion(session_factory, mundo["ana"])
    await insertar_turno(session_factory, mundo, MANANA)
    await ciclo(session_factory, proveedor_gcal)
    await poner_conexion(session_factory, conexion_id, estado="revocada")
    await insertar_turno(session_factory, mundo, MANANA + timedelta(hours=2))
    await ciclo(session_factory, proveedor_gcal)
    assert len(proveedor_gcal.vigentes()) == 1  # revocada: nada se sincroniza
    await poner_conexion(session_factory, conexion_id, estado="activa", sync_token=None)  # volvió a conectar
    await ciclo(session_factory, proveedor_gcal)
    assert len(proveedor_gcal.vigentes()) == 2 and proveedor_gcal.llamadas.count("insertar") == 2
    assert len(await eventos(session_factory, conexion_id)) == 2


async def test_un_token_ilegible_por_clave_rotada_deja_la_conexion_revocada(
        session_factory: Factory, proveedor_gcal: ProveedorFalso) -> None:
    from cryptography.fernet import Fernet

    mundo = await sembrar_mundo(session_factory)
    otra = Fernet.generate_key().decode()
    conexion_id = await sembrar_conexion(
        session_factory, mundo["ana"], refresh_token_cifrado=cifrar("refresh-sintetico-009", otra),
        access_token_cifrado=cifrar("token-sintetico-009", otra))
    assert await ciclo(session_factory, proveedor_gcal) == 0
    assert (await conexion(session_factory, conexion_id)).estado == "revocada" and proveedor_gcal.llamadas == []


async def test_un_token_vencido_se_renueva_y_se_guarda_cifrado(session_factory: Factory,
                                                               proveedor_gcal: ProveedorFalso) -> None:
    from app.integraciones.gcal.cifrado import descifrar

    mundo = await sembrar_mundo(session_factory)
    conexion_id = await sembrar_conexion(session_factory, mundo["ana"], access_expira_en=AHORA)
    assert await ciclo(session_factory, proveedor_gcal) == 1
    fila = await conexion(session_factory, conexion_id)
    assert descifrar(fila.access_token_cifrado, CLAVE_FERNET) == "token-sintetico-renovado"
    assert "renovar_token" in proveedor_gcal.llamadas


async def test_una_conexion_tomada_por_otro_worker_se_saltea_sin_error(session_factory: Factory,
                                                                       proveedor_gcal: ProveedorFalso) -> None:
    from sqlalchemy import func

    mundo = await sembrar_mundo(session_factory)
    conexion_id = await sembrar_conexion(session_factory, mundo["ana"])
    await insertar_turno(session_factory, mundo, MANANA)
    async with session_factory() as otro_worker:
        await otro_worker.execute(select(func.pg_advisory_xact_lock(LOCK_GCAL, conexion_id)))
        assert await ciclo(session_factory, proveedor_gcal) == 0 and proveedor_gcal.llamadas == []
    assert await ciclo(session_factory, proveedor_gcal) == 1 and len(proveedor_gcal.vigentes()) == 1


async def test_sin_credenciales_el_ciclo_no_hace_nada(session_factory: Factory, proveedor_gcal: ProveedorFalso,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    mundo = await sembrar_mundo(session_factory)
    await sembrar_conexion(session_factory, mundo["ana"])
    await insertar_turno(session_factory, mundo, MANANA)
    monkeypatch.delenv("GCAL_CLIENT_SECRET")
    assert await ciclo(session_factory, proveedor_gcal) == 0 and proveedor_gcal.llamadas == []
