"""C-15 (4.1-4.2): login y renovación sobre la sesión; usuarios inactivos; bcrypt de costo parejo. Datos sintéticos (R19)."""

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import func, select, update

from app.models.auth import SesionPanel
from app.models.core import RegistroAuditoria, Rol, Usuario, UsuarioRol
from app.shared.settings import get_settings
from tests.conftest import PASSWORD_PANEL, crear_usuario_panel

EMAIL = "dra.ficticia@turnos.test"
CSRF = {"X-Panel-Csrf": "1"}


@pytest_asyncio.fixture
async def https() -> AsyncIterator[AsyncClient]:
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as ac:
        yield ac


def _claims(token: str) -> dict[str, object]:
    ajustes = get_settings()
    return jwt.decode(token, ajustes.jwt_secret_key, algorithms=[ajustes.jwt_algorithm],
                      options={"verify_exp": False, "verify_iat": False})


def _login(c: AsyncClient, email: str = EMAIL, password: str = PASSWORD_PANEL) -> "asyncio.Future[Response]":
    return c.post("/api/auth/login", json={"email": email, "password": password})  # type: ignore[return-value]


def _tiene_cookie(r: Response) -> bool:
    return any(h.startswith("refresh_token=") for h in r.headers.get_list("set-cookie"))


async def _cantidad_sesiones(factory) -> int:
    async with factory() as s:
        return (await s.execute(select(func.count()).select_from(SesionPanel))).scalar_one()


async def _auditoria(factory, accion: str) -> list[RegistroAuditoria]:
    async with factory() as s:
        return list((await s.execute(select(RegistroAuditoria).where(RegistroAuditoria.accion == accion))).scalars())


# --- 4.1 el login crea la sesión ---------------------------------------------------------------------------------

async def test_login_crea_la_sesion_con_vencimiento_absoluto_y_los_dos_tokens_llevan_su_sid(
        https, session_factory) -> None:
    uid, _ = await crear_usuario_panel(session_factory, EMAIL, ["odontologo"])
    antes = await _cantidad_sesiones(session_factory)
    r = await _login(https)
    assert r.status_code == 200, r.text
    assert await _cantidad_sesiones(session_factory) == antes + 1
    acceso = _claims(r.json()["access_token"])
    cookie = next(h for h in r.headers.get_list("set-cookie") if h.startswith("refresh_token="))
    refresco = _claims(cookie.split(";", 1)[0].split("=", 1)[1])
    assert acceso["sid"] == refresco["sid"] and acceso["jti"] != refresco["jti"]
    async with session_factory() as s:
        fila = (await s.execute(select(SesionPanel).where(SesionPanel.sid == UUID(str(acceso["sid"]))))).scalar_one()
    assert fila.usuario_id == uid
    assert fila.expira_en - fila.creada_en == timedelta(hours=get_settings().sesion_maxima_horas)
    assert fila.refresh_jti == UUID(str(refresco["jti"]))
    assert fila.ip_inicio is not None  # la IP del socket del cliente de pruebas, no un texto inventado


async def test_dos_logins_son_dos_sesiones_independientes(https, session_factory) -> None:
    from app.main import app

    await crear_usuario_panel(session_factory, EMAIL, ["odontologo"])
    # dos equipos = dos jarras de cookies distintas
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as segundo:
        a, b = await _login(https), await _login(segundo)
        sid_a, sid_b = _claims(a.json()["access_token"])["sid"], _claims(b.json()["access_token"])["sid"]
        assert sid_a != sid_b
        cab_b = {"Authorization": f"Bearer {b.json()['access_token']}"}
        assert (await https.post("/api/auth/logout", headers={"Authorization": f"Bearer {a.json()['access_token']}"})
                ).status_code == 200
        assert (await https.get("/api/auth/me", headers={"Authorization": f"Bearer {a.json()['access_token']}"})
                ).status_code == 401
        assert (await segundo.get("/api/auth/me", headers=cab_b)).status_code == 200  # cerrar una no afecta a la otra


async def test_login_fallido_no_crea_sesion(https, session_factory) -> None:
    await crear_usuario_panel(session_factory, EMAIL, ["odontologo"])
    antes = await _cantidad_sesiones(session_factory)
    r = await _login(https, password="contrasena-equivocada-1")
    assert r.status_code == 401 and not _tiene_cookie(r)
    assert await _cantidad_sesiones(session_factory) == antes


# --- 4.2 inactivos, enumeración y renovación ---------------------------------------------------------------------

async def test_usuario_activo_puede_ingresar(https, session_factory) -> None:
    await crear_usuario_panel(session_factory, EMAIL, ["odontologo"])
    assert (await _login(https)).status_code == 200


async def test_usuario_inactivo_con_la_contrasena_correcta_es_el_mismo_401_sin_cookie_ni_sesion(
        https, session_factory) -> None:
    uid, _ = await crear_usuario_panel(session_factory, EMAIL, ["odontologo"])
    async with session_factory() as s:
        await s.execute(update(Usuario).where(Usuario.id == uid).values(is_active=False))
        await s.commit()
    antes = await _cantidad_sesiones(session_factory)
    inactivo = await _login(https)
    equivocada = await _login(https, password="contrasena-equivocada-1")
    assert inactivo.status_code == 401 and not _tiene_cookie(inactivo)
    assert inactivo.json() == equivocada.json() == {"detail": "Credenciales inválidas"}
    assert await _cantidad_sesiones(session_factory) == antes
    fallos = await _auditoria(session_factory, "LOGIN_FAILED")
    assert sorted(f.datos_despues["motivo"] for f in fallos) == ["credenciales", "usuario_inactivo"]


async def test_email_inexistente_es_el_mismo_401_y_se_verifica_el_hash_ficticio(
        https, session_factory, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.auth import router as router_auth

    await crear_usuario_panel(session_factory, EMAIL, ["odontologo"])
    verificados: list[str] = []
    real = router_auth.verify_password

    def espia(plano: str, hash_: str) -> bool:
        verificados.append(hash_)
        return real(plano, hash_)

    monkeypatch.setattr(router_auth, "verify_password", espia)
    r = await _login(https, email="inexistente@turnos.test")
    assert r.status_code == 401 and r.json() == {"detail": "Credenciales inválidas"}
    assert len(verificados) == 1 and verificados[0].startswith("$2")  # bcrypt corrió igual, contra un hash ficticio
    existente = await _login(https, password="contrasena-equivocada-1")
    assert len(verificados) == 2 and verificados[1] != verificados[0]
    assert existente.json() == r.json()


async def test_el_email_se_normaliza_al_ingresar(https, session_factory) -> None:
    await crear_usuario_panel(session_factory, EMAIL, ["odontologo"])
    assert (await _login(https, email="  Dra.Ficticia@Turnos.TEST ")).status_code == 200


async def test_la_renovacion_emite_los_roles_de_la_base(https, session_factory) -> None:
    uid, _ = await crear_usuario_panel(session_factory, "rita.ficticia@turnos.test", ["recepcion"])
    assert (await _login(https, email="rita.ficticia@turnos.test")).status_code == 200
    async with session_factory() as s:
        admin = (await s.execute(select(Rol).where(Rol.nombre == "admin"))).scalar_one_or_none()
        if admin is None:
            admin = Rol(nombre="admin")
            s.add(admin)
            await s.flush()
        s.add(UsuarioRol(usuario_id=uid, rol_id=admin.id))
        await s.commit()
    r = await https.post("/api/auth/refresh", headers=CSRF)
    assert r.status_code == 200
    assert sorted(_claims(r.json()["access_token"])["roles"]) == ["admin", "recepcion"]


async def test_renovar_con_el_usuario_desactivado_por_sql_es_401_y_borra_la_cookie(https, session_factory) -> None:
    uid, _ = await crear_usuario_panel(session_factory, EMAIL, ["odontologo"])
    assert (await _login(https)).status_code == 200
    async with session_factory() as s:  # desactivado sin revocar sus sesiones
        await s.execute(update(Usuario).where(Usuario.id == uid).values(is_active=False))
        await s.commit()
    r = await https.post("/api/auth/refresh", headers=CSRF)
    assert r.status_code == 401 and "access_token" not in r.text
    cookie = next(h for h in r.headers.get_list("set-cookie") if h.startswith("refresh_token=")).lower()
    assert "max-age=0" in cookie or "1970" in cookie


async def test_dos_renovaciones_simultaneas_un_200_un_401_y_la_sesion_sigue_para_la_ganadora(
        https, session_factory) -> None:
    await crear_usuario_panel(session_factory, EMAIL, ["odontologo"])
    await _login(https)
    a, b = await asyncio.gather(https.post("/api/auth/refresh", headers=CSRF),
                                https.post("/api/auth/refresh", headers=CSRF))
    assert sorted([a.status_code, b.status_code]) == [200, 401]
    ganadora = a if a.status_code == 200 else b
    assert (await https.get("/api/auth/me", headers={"Authorization": f"Bearer {ganadora.json()['access_token']}"})
            ).status_code == 200
    async with session_factory() as s:
        vigente = (await s.execute(select(func.count()).select_from(SesionPanel)
                                   .where(SesionPanel.revocada_en.is_(None), SesionPanel.expira_en > datetime.now(timezone.utc))
                                   )).scalar_one()
    assert vigente >= 1
