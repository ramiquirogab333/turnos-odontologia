"""C-16 (2.3): ``GET /api/panel/obras-sociales``. PostgreSQL real. Datos sintéticos (R19)."""

from httpx import AsyncClient

from tests.clinica_helpers import Escenario, crear_obra_social, sembrar_escenario
from tests.conftest import bearer

URL = "/api/panel/obras-sociales"


async def test_recepcion_lista_las_activas_por_nombre_con_solo_id_y_nombre(session_factory, client: AsyncClient) -> None:  # type: ignore[no-untyped-def]
    esc: Escenario = await sembrar_escenario(session_factory)
    swiss = await crear_obra_social(session_factory, "SWISS", "Swiss Medical")
    osde = await crear_obra_social(session_factory, "OSDE", "OSDE")
    await crear_obra_social(session_factory, "VIEJA", "Obra Vieja", activa=False)
    resp = await client.get(URL, headers=bearer(esc.recepcion))
    assert resp.status_code == 200, resp.text
    assert resp.json() == [{"id": osde, "nombre": "OSDE"}, {"id": swiss, "nombre": "Swiss Medical"}]
    admin = await client.get(URL, headers=bearer(esc.admin))
    assert admin.status_code == 200 and len(admin.json()) == 2


async def test_la_odontologa_recibe_403_y_sin_token_401(session_factory, client: AsyncClient) -> None:  # type: ignore[no-untyped-def]
    esc = await sembrar_escenario(session_factory)
    assert (await client.get(URL, headers=bearer(esc.ana))).status_code == 403
    assert (await client.get(URL)).status_code == 401


async def test_sin_obras_sociales_activas_devuelve_lista_vacia(session_factory, client: AsyncClient) -> None:  # type: ignore[no-untyped-def]
    esc = await sembrar_escenario(session_factory)
    await crear_obra_social(session_factory, "VIEJA", "Obra Vieja", activa=False)
    resp = await client.get(URL, headers=bearer(esc.recepcion))
    assert resp.status_code == 200 and resp.json() == []
