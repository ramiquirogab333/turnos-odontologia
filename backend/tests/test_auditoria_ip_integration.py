"""C-15 (5.3): la auditoría de acceso y del catálogo guarda la IP real del cliente, nunca un texto fijo. R19: IPs de documentación."""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.models.core import RegistroAuditoria
from tests.conftest import PASSWORD_PANEL, bearer, crear_usuario_panel

EMAIL = "recepcion@turnos.test"


def _cliente(socket: tuple[str, int] | None) -> AsyncClient:
    from app.main import app

    return AsyncClient(transport=ASGITransport(app=app, client=socket), base_url="https://test")


async def _registros(factory, accion: str) -> list[RegistroAuditoria]:
    async with factory() as s:
        return list((await s.execute(select(RegistroAuditoria).where(RegistroAuditoria.accion == accion)
                                     .order_by(RegistroAuditoria.id))).scalars())


async def test_login_ok_y_fallido_guardan_la_ip_del_socket(session_factory) -> None:
    await crear_usuario_panel(session_factory, EMAIL, ["recepcion"])
    async with _cliente(("198.51.100.21", 4000)) as c:
        assert (await c.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD_PANEL})).status_code == 200
        assert (await c.post("/api/auth/login", json={"email": EMAIL, "password": "equivocada-123"})).status_code == 401
        assert (await c.post("/api/auth/login", json={"email": "nadie@turnos.test", "password": "equivocada-123"})
                ).status_code == 401
    assert [r.ip for r in await _registros(session_factory, "LOGIN_OK")] == ["198.51.100.21"]
    assert [r.ip for r in await _registros(session_factory, "LOGIN_FAILED")] == ["198.51.100.21"] * 2


async def test_logout_guarda_la_ip_del_socket(session_factory) -> None:
    await crear_usuario_panel(session_factory, EMAIL, ["recepcion"])
    async with _cliente(("203.0.113.7", 4000)) as c:
        login = await c.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD_PANEL})
        await c.post("/api/auth/logout", headers=bearer(login.json()["access_token"]))
    assert [r.ip for r in await _registros(session_factory, "LOGOUT")] == ["203.0.113.7"]


async def test_sin_ip_conocida_el_campo_queda_nulo_nunca_un_texto_inventado(session_factory) -> None:
    await crear_usuario_panel(session_factory, EMAIL, ["recepcion"])
    async with _cliente(None) as c:
        login = await c.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD_PANEL})
        await c.post("/api/auth/logout", headers=bearer(login.json()["access_token"]))
    for accion in ("LOGIN_OK", "LOGOUT"):
        assert [r.ip for r in await _registros(session_factory, accion)] == [None], accion


async def test_el_catalogo_audita_con_la_ip_real(session_factory) -> None:
    _, token = await crear_usuario_panel(session_factory, "admin@turnos.test", ["admin"])
    async with _cliente(("192.0.2.44", 4000)) as c:
        r = await c.post("/api/admin/tratamientos", headers=bearer(token),
                         json={"nombre": "Limpieza sintética", "duracion_minutos": 30, "precio_base": "1000.00"})
    assert r.status_code == 201, r.text
    creados = await _registros(session_factory, "CREATE")
    assert creados and all(x.ip == "192.0.2.44" for x in creados)


@pytest.mark.parametrize("modulo", ["app/auth/router.py", "app/catalogo/router.py", "app/catalogo/service.py"])
def test_no_queda_el_texto_testclient_en_el_codigo(modulo: str) -> None:
    from pathlib import Path

    assert "testclient" not in (Path(__file__).resolve().parents[1] / "src" / modulo).read_text(encoding="utf-8")
