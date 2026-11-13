"""C-13 (8.5, D10, O15): una exportación en curso por usuario y N por hora, con el limitador de C-15. Reloj inyectado."""

from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select

from app.models.core import RegistroAuditoria
from app.shared.limites import LimitadorEnMemoria, get_limitador_base
from tests.clinica_helpers import Escenario, sembrar_escenario
from tests.conftest import bearer
from tests.test_exportacion_streaming_integration import descargar

URL = "/api/panel/export"
AHORA = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
async def esc(session_factory, reloj) -> Escenario:  # type: ignore[no-untyped-def]
    reloj(AHORA)
    return await sembrar_escenario(session_factory)


@pytest.fixture
def segundos() -> list[float]:
    return [1000.0]


@pytest.fixture(autouse=True)
async def limitador_con_reloj(segundos: list[float]) -> AsyncIterator[LimitadorEnMemoria]:
    from app.main import app

    memoria = LimitadorEnMemoria(reloj=lambda: segundos[0])
    app.dependency_overrides[get_limitador_base] = lambda: memoria
    yield memoria
    app.dependency_overrides.pop(get_limitador_base, None)


async def exportar(client: AsyncClient, token: str, entidad: str = "turnos") -> Response:
    return await client.get(URL, params={"entidad": entidad, "formato": "csv"}, headers=bearer(token))


async def exportaciones(factory) -> int:  # type: ignore[no-untyped-def]
    async with factory() as s:
        return len((await s.execute(select(RegistroAuditoria.id).where(RegistroAuditoria.accion == "exportacion"))).all())


async def test_tres_exportaciones_seguidas_terminadas_responden_200(client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    assert [(await exportar(client, esc.recepcion)).status_code for _ in range(3)] == [200, 200, 200]


async def test_la_numero_21_en_la_hora_da_429_con_retry_after_y_sin_registro_y_pasada_la_hora_vuelve(
        session_factory, client: AsyncClient, esc, segundos: list[float]) -> None:  # type: ignore[no-untyped-def]
    for _ in range(20):
        assert (await exportar(client, esc.recepcion)).status_code == 200
    segundos[0] += 600  # pasaron 10 minutos
    r = await exportar(client, esc.recepcion)
    assert r.status_code == 429 and r.json()["motivo"] == "demasiados_intentos"
    assert 1 <= int(r.headers["retry-after"]) <= 3000 and not r.content.startswith(b"\xef\xbb\xbf")
    assert await exportaciones(session_factory) == 20
    assert (await exportar(client, esc.admin)).status_code == 200  # el límite es por usuario
    segundos[0] += 3000  # vence la ventana de la hora
    assert (await exportar(client, esc.recepcion)).status_code == 200


async def test_una_segunda_exportacion_simultanea_da_429_la_primera_termina_y_despues_se_libera_el_lease(
        session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    segunda: list[Response] = []

    async def pedir_otra() -> None:
        segunda.append(await exportar(client, esc.recepcion))

    estado, cuerpo, _ = await descargar(esc.recepcion, en_primer_trozo=pedir_otra, entidad="turnos")
    assert estado == 200 and cuerpo.startswith(b"\xef\xbb\xbfid,inicio")  # la primera terminó normalmente
    assert segunda[0].status_code == 429 and segunda[0].json()["motivo"] == "demasiados_intentos"
    assert await exportaciones(session_factory) == 1
    assert (await exportar(client, esc.recepcion)).status_code == 200  # el lease se liberó al terminar


async def test_dos_usuarios_distintos_exportan_a_la_vez(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    otra: list[Response] = []

    async def pedir_admin() -> None:
        otra.append(await exportar(client, esc.admin))

    estado, _, _ = await descargar(esc.recepcion, en_primer_trozo=pedir_admin, entidad="turnos")
    assert (estado, otra[0].status_code) == (200, 200)


async def test_los_rechazos_por_permiso_no_consumen_el_cupo(client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    for _ in range(25):
        assert (await exportar(client, esc.recepcion, "pacientes")).status_code == 403
    assert (await exportar(client, esc.recepcion)).status_code == 200


async def test_con_el_almacen_caido_se_exporta_igual_fail_open_de_c15(client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    from app.main import app

    class Caido:
        async def consumir(self, *a: Any, **k: Any) -> Any:
            raise ConnectionError("redis caído (simulado)")

        registrar = consultar = reiniciar = consumir

    app.dependency_overrides[get_limitador_base] = lambda: Caido()
    assert (await exportar(client, esc.recepcion)).status_code == 200
