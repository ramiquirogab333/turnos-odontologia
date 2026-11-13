"""C-15 (6.3): adaptador Redis del limitador contra un Redis real.

Requiere ``REDIS_URL``. Sin Redis local se salta con motivo explícito; en CI (variable ``CI``) nunca se salta: si falta
``REDIS_URL`` el test falla para que no pase en silencio. Cada test usa claves únicas (prefijo aleatorio) y las borra.
"""

import asyncio
import os
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from redis.asyncio import Redis

from app.shared.limites import LimitadorRedis, LimitadorTolerante

REDIS_URL = os.environ.get("REDIS_URL")


@pytest_asyncio.fixture
async def redis() -> AsyncIterator["Redis[str]"]:
    if not REDIS_URL:
        if os.environ.get("CI"):
            pytest.fail("En CI REDIS_URL es obligatoria: el job backend debe levantar el servicio redis")
        pytest.skip("sin REDIS_URL: levantá Redis (docker compose up -d redis) y exportá REDIS_URL para este test")
    cliente: Redis[str] = Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        await cliente.ping()
    except Exception:  # noqa: BLE001
        await cliente.aclose()
        if os.environ.get("CI"):
            pytest.fail("En CI Redis tiene que responder")
        pytest.skip("REDIS_URL no responde desde este equipo (¿el puerto de Redis está publicado?)")
    try:
        yield cliente
    finally:
        async for clave in cliente.scan_iter(match="rl:test:*"):
            await cliente.delete(clave)
        await cliente.aclose()


def _clave() -> str:
    return f"rl:test:{uuid4().hex}"


async def test_permite_hasta_el_maximo_y_rechaza_el_siguiente(redis) -> None:
    limitador, clave = LimitadorRedis(redis), _clave()
    assert [(await limitador.consumir(clave, 3, 60)).permitido for _ in range(4)] == [True, True, True, False]


async def test_el_ttl_alimenta_retry_after_y_la_ventana_no_se_extiende(redis) -> None:
    limitador, clave = LimitadorRedis(redis), _clave()
    await limitador.consumir(clave, 1, 100)
    rechazo = await limitador.consumir(clave, 1, 100)
    assert 1 <= rechazo.reintentar_en_segundos <= 100
    assert 0 < await redis.ttl(clave) <= 100  # el EXPIRE NX no se reinicia con cada pedido


async def test_incr_y_expire_son_atomicos_bajo_concurrencia_y_hay_ttl(redis) -> None:
    limitador, clave = LimitadorRedis(redis), _clave()
    resultados = await asyncio.gather(*[limitador.consumir(clave, 10, 60) for _ in range(50)])
    assert sum(r.permitido for r in resultados) == 10
    assert sum(r.recien_bloqueado for r in resultados) == 1
    assert await redis.ttl(clave) > 0


async def test_dos_procesos_comparten_el_contador(redis) -> None:
    otro: Redis[str] = Redis.from_url(REDIS_URL or "", decode_responses=True)
    try:
        a, b, clave = LimitadorRedis(redis), LimitadorRedis(otro), _clave()
        assert (await a.consumir(clave, 2, 60)).permitido and (await b.consumir(clave, 2, 60)).permitido
        assert not (await a.consumir(clave, 2, 60)).permitido
    finally:
        await otro.aclose()


async def test_consultar_no_suma_y_reiniciar_borra(redis) -> None:
    limitador, clave = LimitadorRedis(redis), _clave()
    assert (await limitador.consultar(clave, 2)).permitido
    await limitador.registrar(clave, 60)
    await limitador.registrar(clave, 60)
    bloqueado = await limitador.consultar(clave, 2)
    assert not bloqueado.permitido and bloqueado.recien_bloqueado and 1 <= bloqueado.reintentar_en_segundos <= 60
    assert not (await limitador.consultar(clave, 2)).recien_bloqueado  # el aviso es una sola vez
    await limitador.reiniciar(clave)
    assert (await limitador.consultar(clave, 2)).permitido


async def test_la_clave_no_contiene_el_email_en_claro(redis) -> None:
    from app.shared.limites import clave_email

    clave = f"rl:test:{clave_email('Recepcion@Turnos.test')}"
    await LimitadorRedis(redis).registrar(clave, 60)
    claves = [k async for k in redis.scan_iter(match="rl:test:*")]
    assert clave in claves and not any("recepcion" in k.lower() or "turnos.test" in k for k in claves)


async def test_redis_caido_o_lento_deja_pasar_con_un_unico_aviso(caplog: pytest.LogCaptureFixture) -> None:
    import logging

    muerto: Redis[str] = Redis.from_url("redis://127.0.0.1:1/0", decode_responses=True)  # puerto sin servicio
    LimitadorTolerante._ultimo_aviso = float("-inf")
    tolerante = LimitadorTolerante(LimitadorRedis(muerto), timeout_ms=200)
    caplog.set_level(logging.WARNING)
    try:
        for _ in range(3):
            assert (await tolerante.consumir(_clave(), 1, 60)).permitido
        assert (await tolerante.consultar(_clave(), 1)).permitido
    finally:
        await muerto.aclose()
    avisos = [r.getMessage() for r in caplog.records if "limite no aplicado" in r.getMessage()]
    assert len(avisos) == 1 and "127.0.0.1" not in avisos[0]
