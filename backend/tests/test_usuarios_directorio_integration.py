"""C-13 (6.4, O3): ``GET /api/panel/usuarios`` — directorio mínimo para filtrar la auditoría. Datos sintéticos (R19)."""

from httpx import AsyncClient
from sqlalchemy import update

from app.models.core import Usuario
from tests.conftest import bearer, crear_usuario_panel

URL = "/api/panel/usuarios"


async def test_el_admin_recibe_id_nombre_y_estado_sin_email_ni_roles(session_factory, client: AsyncClient) -> None:  # type: ignore[no-untyped-def]
    _, admin = await crear_usuario_panel(session_factory, "admin@turnos.test", ["admin"])
    recep_id, _ = await crear_usuario_panel(session_factory, "recepcion@turnos.test", ["recepcion"])
    r = await client.get(URL, headers=bearer(admin))
    assert r.status_code == 200, r.text
    assert len(r.json()) == 2 and {u["id"] for u in r.json()} >= {recep_id}
    assert all(set(u) == {"id", "nombre_completo", "activo"} for u in r.json())
    assert "recepcion@turnos.test" not in r.text and "roles" not in r.text


async def test_recepcion_odontologa_y_sin_sesion_no_reciben_ningun_usuario(session_factory, client: AsyncClient) -> None:  # type: ignore[no-untyped-def]
    _, recep = await crear_usuario_panel(session_factory, "recepcion@turnos.test", ["recepcion"])
    _, ana = await crear_usuario_panel(session_factory, "dra.ficticia@turnos.test", ["odontologo"])
    for token in (recep, ana):
        r = await client.get(URL, headers=bearer(token))
        assert r.status_code == 403 and "nombre_completo" not in r.text
    assert (await client.get(URL)).status_code == 401


async def test_un_usuario_desactivado_aparece_marcado_inactivo(session_factory, client: AsyncClient) -> None:  # type: ignore[no-untyped-def]
    _, admin = await crear_usuario_panel(session_factory, "admin@turnos.test", ["admin"])
    baja_id, _ = await crear_usuario_panel(session_factory, "ex.recepcion@turnos.test", ["recepcion"])
    async with session_factory() as s:
        await s.execute(update(Usuario).where(Usuario.id == baja_id).values(is_active=False))
        await s.commit()
    estados = {u["id"]: u["activo"] for u in (await client.get(URL, headers=bearer(admin))).json()}
    assert estados[baja_id] is False and list(estados.values()).count(True) == 1
