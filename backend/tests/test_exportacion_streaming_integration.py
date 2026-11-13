"""C-13 (8.4, D9, R16): la exportación grande se entrega por partes, con una foto consistente y sin frenar la API. Sintético."""

import asyncio
import tracemalloc
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.turnos.models import Turno
from tests.clinica_helpers import Escenario, sembrar_escenario
from tests.conftest import bearer

URL = "/api/panel/export"
AHORA = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
INICIO0 = datetime(2027, 1, 4, 12, 0, tzinfo=timezone.utc)
Factory = async_sessionmaker[AsyncSession]


@pytest.fixture
async def esc(session_factory, reloj) -> Escenario:  # type: ignore[no-untyped-def]
    reloj(AHORA)
    return await sembrar_escenario(session_factory)


async def sembrar_turnos(factory: Factory, esc: Escenario, cantidad: int, estado: str) -> None:
    """``cantidad`` turnos consecutivos de 30 minutos (sin solape) de una misma profesional y sillón."""
    base = {"profesional_id": esc.mundo["ana"], "sillon_id": esc.mundo["s1"], "tratamiento_id": esc.mundo["trat"],
            "estado": estado, "origen": "web"}
    async with factory() as s:
        for desde in range(0, cantidad, 10_000):
            filas = [{**base, "inicio": INICIO0 + timedelta(minutes=30 * n), "fin": INICIO0 + timedelta(minutes=30 * n + 30)}
                     for n in range(desde, min(desde + 10_000, cantidad))]
            await s.execute(insert(Turno), filas)
        await s.commit()


def _scope(token: str, **query: str) -> dict[str, Any]:
    cadena = "&".join(f"{k}={v}" for k, v in {"formato": "csv", **query}.items())
    return {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"}, "http_version": "1.1", "method": "GET",
            "scheme": "http", "path": URL, "raw_path": URL.encode(), "root_path": "", "query_string": cadena.encode(),
            "client": ("203.0.113.5", 1234), "server": ("test", 80),
            "headers": [(b"host", b"test"), (b"authorization", f"Bearer {token}".encode())]}


async def descargar(token: str, *, en_primer_trozo: Callable[[], Awaitable[None]] | None = None,
                    guardar: bool = True, **query: str) -> tuple[int, bytes, int]:
    """Corre la app por ASGI y devuelve ``(estado, cuerpo, líneas)``; el gancho corre con la descarga ya empezada."""
    from app.main import app

    estado = 0
    trozos: list[bytes] = []
    lineas = 0
    hecho = False

    async def receive() -> dict[str, Any]:
        await asyncio.Event().wait()  # el cliente no corta
        return {"type": "http.disconnect"}

    async def send(mensaje: dict[str, Any]) -> None:
        nonlocal estado, lineas, hecho
        if mensaje["type"] == "http.response.start":
            estado = mensaje["status"]
        elif mensaje["type"] == "http.response.body":
            cuerpo = mensaje.get("body", b"")
            lineas += cuerpo.count(b"\r\n")
            if guardar:
                trozos.append(cuerpo)
            if not hecho and en_primer_trozo is not None:
                hecho = True
                await en_primer_trozo()

    await app(_scope(token, **query), receive, send)  # type: ignore[arg-type]
    return estado, b"".join(trozos), lineas


async def test_la_foto_es_consistente_aunque_un_update_concurrente_cambie_estados_entre_lotes(
        session_factory, esc) -> None:  # type: ignore[no-untyped-def]
    await sembrar_turnos(session_factory, esc, 1300, "reservado")

    async def cancelar_todo() -> None:
        async with session_factory() as s:
            await s.execute(update(Turno).values(estado="cancelado"))
            await s.commit()

    estado, cuerpo, _ = await descargar(esc.recepcion, en_primer_trozo=cancelar_todo, entidad="turnos")
    assert estado == 200
    filas = [f.split(",") for f in cuerpo.decode("utf-8-sig").strip().split("\r\n")]
    assert len(filas) == 1301
    ids = [int(f[0]) for f in filas[1:]]
    assert ids == sorted(set(ids)) and len(ids) == 1300  # sin duplicados ni faltantes, en orden
    assert {f[3] for f in filas[1:]} == {"reservado"}  # el estado que tenían al empezar
    async with session_factory() as s:
        assert {e for (e,) in (await s.execute(select(Turno.estado).distinct())).all()} == {"cancelado"}


async def test_otra_peticion_responde_mientras_la_exportacion_esta_en_curso(
        session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await sembrar_turnos(session_factory, esc, 1300, "reservado")
    respuestas: list[int] = []

    async def pedir_agenda() -> None:
        r = await asyncio.wait_for(client.get("/api/panel/agenda", params={"vista": "dia", "fecha": "2026-11-13"}, headers=bearer(esc.admin)), timeout=10)
        respuestas.append(r.status_code)

    estado, _, lineas = await descargar(esc.recepcion, en_primer_trozo=pedir_agenda, entidad="turnos")
    assert (estado, respuestas, lineas) == (200, [200], 1301)


@pytest.mark.slow
async def test_cien_mil_turnos_se_exportan_con_memoria_acotada(session_factory, esc) -> None:  # type: ignore[no-untyped-def]
    await sembrar_turnos(session_factory, esc, 100_000, "cancelado")
    tracemalloc.start()
    try:
        estado, _, lineas = await descargar(esc.admin, guardar=False, entidad="turnos")
        _, pico = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert (estado, lineas) == (200, 100_001)
    # El CSV completo pesa más de 10 MB: con el cuerpo armado en memoria el pico lo superaría de lejos.
    assert pico < 8 * 1024 * 1024, f"pico de memoria {pico / 1024 / 1024:.1f} MiB"
