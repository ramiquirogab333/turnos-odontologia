"""C-08 (3.x, O2, D10) y C-15 (4.1): refresh en cookie HttpOnly, CSRF y logout sobre la sesión del servidor.

El cliente usa ``https://test``: ``http.cookiejar`` no reenvía una cookie ``Secure`` por ``http://``.
Datos sintéticos (R19). Desde C-15 la revocación vive en ``sesion_panel`` (no hay ``token_blacklist``) y un segundo
logout con el mismo access responde 401 (la sesión ya está cerrada), nunca 500.
"""

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
import pytest_asyncio
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import func, select

from app.auth.service import create_access_token, decode_token
from app.models.auth import SesionPanel
from app.models.core import RegistroAuditoria
from app.shared.settings import get_settings
from tests.conftest import PASSWORD_PANEL, crear_usuario_panel

EMAIL = "recepcion@turnos.test"
CSRF = {"X-Panel-Csrf": "1"}


@pytest_asyncio.fixture
async def https() -> AsyncIterator[AsyncClient]:
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def usuario(session_factory, clean_db) -> int:
    uid, _ = await crear_usuario_panel(session_factory, EMAIL, ["recepcion"])
    return uid


async def _login(c: AsyncClient) -> Response:
    return await c.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD_PANEL})


def _cookie_de(r: Response) -> str:
    return next(h for h in r.headers.get_list("set-cookie") if h.startswith("refresh_token="))


def _valor(set_cookie: str) -> str:
    return set_cookie.split(";", 1)[0].split("=", 1)[1]


def _borrada(r: Response) -> bool:
    c = _cookie_de(r).lower()
    return "max-age=0" in c or "1970" in c


async def _jti_vigente(factory, jti: str) -> bool:
    """True si ``jti`` es hoy el único refresh vigente de alguna sesión."""
    async with factory() as s:
        return (await s.execute(select(func.count()).select_from(SesionPanel)
                                .where(SesionPanel.refresh_jti == UUID(jti)))).scalar_one() == 1


async def _sesion_revocada(factory, sid: str) -> bool:
    async with factory() as s:
        fila = (await s.execute(select(SesionPanel).where(SesionPanel.sid == UUID(sid)))).scalar_one()
        return fila.revocada_en is not None and fila.motivo_revocacion == "logout"


# --- 3.2 contrato de login y refresh -------------------------------------------------------------------

async def test_login_no_devuelve_el_refresh_en_el_json_y_lo_pone_en_una_cookie_endurecida(https, usuario) -> None:
    r = await _login(https)
    assert r.status_code == 200, r.text
    assert set(r.json()) == {"access_token", "token_type"}
    atributos = _cookie_de(r).lower()
    for esperado in ("httponly", "secure", "samesite=strict", "path=/api/auth"):
        assert esperado in atributos, atributos
    assert "domain=" not in atributos
    assert "max-age=" in atributos or "expires=" in atributos


async def test_refresh_con_cookie_y_cabecera_rota_y_reemplaza_la_cookie(https, usuario, session_factory) -> None:
    login = await _login(https)
    viejo = _valor(_cookie_de(login))
    r = await https.post("/api/auth/refresh", headers=CSRF)
    assert r.status_code == 200, r.text
    assert set(r.json()) == {"access_token", "token_type"}
    nuevo = _valor(_cookie_de(r))
    assert nuevo != viejo
    atributos = _cookie_de(r).lower()
    assert "httponly" in atributos and "secure" in atributos and "samesite=strict" in atributos
    assert not await _jti_vigente(session_factory, decode_token(viejo)["jti"])
    assert await _jti_vigente(session_factory, decode_token(nuevo)["jti"])
    assert decode_token(viejo)["sid"] == decode_token(nuevo)["sid"]  # misma sesión, jti nuevo
    # la cookie guardada por el cliente es la nueva: una segunda renovación funciona
    assert (await https.post("/api/auth/refresh", headers=CSRF)).status_code == 200


async def test_el_access_nuevo_del_refresh_sirve_para_me(https, usuario) -> None:
    await _login(https)
    r = await https.post("/api/auth/refresh", headers=CSRF)
    me = await https.get("/api/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert me.status_code == 200 and me.json()["email"] == EMAIL


async def test_sin_la_cabecera_csrf_es_403_y_no_rota_nada(https, usuario, session_factory) -> None:
    login = await _login(https)
    viejo = _valor(_cookie_de(login))
    r = await https.post("/api/auth/refresh")
    assert r.status_code == 403 and r.json()["motivo"] == "csrf_requerido"
    assert await _jti_vigente(session_factory, decode_token(viejo)["jti"])
    assert (await https.post("/api/auth/refresh", headers=CSRF)).status_code == 200  # la cookie seguía vigente


async def test_cabecera_csrf_con_otro_valor_tambien_es_403(https, usuario) -> None:
    await _login(https)
    r = await https.post("/api/auth/refresh", headers={"X-Panel-Csrf": "0"})
    assert r.status_code == 403 and r.json()["motivo"] == "csrf_requerido"


async def test_sin_cookie_es_401_y_borra_la_cookie(https, usuario) -> None:
    r = await https.post("/api/auth/refresh", headers=CSRF)
    assert r.status_code == 401
    assert _borrada(r)


async def test_cookie_basura_es_401_y_borra_la_cookie(https, usuario) -> None:
    https.cookies.set("refresh_token", "no-es-un-jwt", domain="test", path="/api/auth")
    r = await https.post("/api/auth/refresh", headers=CSRF)
    assert r.status_code == 401 and _borrada(r)


async def test_cookie_con_un_token_de_acceso_es_401(https, usuario) -> None:
    uid = usuario
    acceso = create_access_token({"sub": str(uid), "roles": ["recepcion"], "email": EMAIL, "jti": "jti-acceso-sint",
                                  "sid": "00000000-0000-4000-8000-000000000001"})
    https.cookies.set("refresh_token", acceso, domain="test", path="/api/auth")
    r = await https.post("/api/auth/refresh", headers=CSRF)
    assert r.status_code == 401 and _borrada(r)


async def test_el_refresh_por_body_no_se_acepta(https, usuario) -> None:
    login = await _login(https)
    viejo = _valor(_cookie_de(login))
    https.cookies.clear()  # sin cookie: solo el body
    r = await https.post("/api/auth/refresh", headers=CSRF, json={"refresh_token": viejo})
    assert r.status_code == 401


async def test_el_segundo_uso_del_mismo_refresh_es_401(https, usuario) -> None:
    login = await _login(https)
    viejo = _valor(_cookie_de(login))
    assert (await https.post("/api/auth/refresh", headers=CSRF)).status_code == 200
    https.cookies.clear()
    https.cookies.set("refresh_token", viejo, domain="test", path="/api/auth")  # alguien reusa el robado
    r = await https.post("/api/auth/refresh", headers=CSRF)
    assert r.status_code == 401 and _borrada(r)


async def test_cookie_con_refresh_revocado_es_401(https, usuario, session_factory) -> None:
    login = await _login(https)
    sid = decode_token(_valor(_cookie_de(login)))["sid"]
    async with session_factory() as s:
        fila = (await s.execute(select(SesionPanel).where(SesionPanel.sid == UUID(sid)))).scalar_one()
        fila.revocada_en = datetime.now(timezone.utc)
        fila.motivo_revocacion = "logout"
        await s.commit()
    r = await https.post("/api/auth/refresh", headers=CSRF)
    assert r.status_code == 401 and _borrada(r)


async def test_dos_refresh_simultaneos_con_la_misma_cookie_son_un_200_y_un_401_nunca_500(https, usuario) -> None:
    await _login(https)
    a, b = await asyncio.gather(https.post("/api/auth/refresh", headers=CSRF),
                                https.post("/api/auth/refresh", headers=CSRF))
    assert sorted([a.status_code, b.status_code]) == [200, 401]


async def test_el_refresh_vencido_es_401(https, usuario) -> None:
    ajustes = get_settings()
    vencido = jwt.encode({"sub": str(usuario), "roles": ["recepcion"], "email": EMAIL, "jti": "jti-venc",
                          "sid": "00000000-0000-4000-8000-000000000001", "type": "refresh", "iat": datetime.now(timezone.utc) - timedelta(days=9),
                          "exp": datetime.now(timezone.utc) - timedelta(days=2)},
                         ajustes.jwt_secret_key, algorithm=ajustes.jwt_algorithm)
    https.cookies.set("refresh_token", vencido, domain="test", path="/api/auth")
    r = await https.post("/api/auth/refresh", headers=CSRF)
    assert r.status_code == 401 and _borrada(r)


# --- 3.4 logout ---------------------------------------------------------------------------------------------

async def test_logout_revoca_la_sesion_borra_la_cookie_y_ni_el_refresh_ni_el_access_sirven(
        https, usuario, session_factory) -> None:
    login = await _login(https)
    access = login.json()["access_token"]
    cab = {"Authorization": f"Bearer {access}"}
    refresh = _valor(_cookie_de(login))
    r = await https.post("/api/auth/logout", headers=cab)
    assert r.status_code == 200 and _borrada(r)
    assert await _sesion_revocada(session_factory, decode_token(access)["sid"])
    https.cookies.set("refresh_token", refresh, domain="test", path="/api/auth")
    assert (await https.post("/api/auth/refresh", headers=CSRF)).status_code == 401
    assert (await https.get("/api/auth/me", headers=cab)).status_code == 401  # el access sigue vigente por 15 min


async def test_el_refresh_revocado_por_logout_sigue_revocado_a_los_16_minutos(https, usuario, reloj) -> None:
    login = await _login(https)
    refresh = _valor(_cookie_de(login))
    cab = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert (await https.post("/api/auth/logout", headers=cab)).status_code == 200
    reloj(datetime.now(timezone.utc) + timedelta(minutes=16))  # dentro de la duración máxima de la sesión
    https.cookies.set("refresh_token", refresh, domain="test", path="/api/auth")
    r = await https.post("/api/auth/refresh", headers=CSRF)
    assert r.status_code == 401


async def test_el_segundo_logout_con_el_mismo_access_es_401_nunca_500(https, usuario) -> None:
    login = await _login(https)
    cab = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert (await https.post("/api/auth/logout", headers=cab)).status_code == 200
    assert (await https.post("/api/auth/logout", headers=cab)).status_code == 401


async def test_logout_con_un_access_vigente_y_una_cookie_ya_rotada_revoca_la_sesion_entera(
        https, usuario, session_factory) -> None:
    login = await _login(https)
    access_viejo = login.json()["access_token"]
    jti_viejo = decode_token(access_viejo)["jti"]
    rotado = await https.post("/api/auth/refresh", headers=CSRF)  # otra pestaña rota: la cookie ahora es de otro jti
    jti_cookie = decode_token(_valor(_cookie_de(rotado)))["jti"]
    assert jti_cookie != jti_viejo
    # el access de la otra pestaña (el rotado) sigue valiendo: no se revoca por rotar
    assert (await https.get("/api/auth/me", headers={"Authorization": f"Bearer {rotado.json()['access_token']}"})
            ).status_code == 200
    assert (await https.post("/api/auth/logout", headers={"Authorization": f"Bearer {access_viejo}"})).status_code == 200
    sid = decode_token(access_viejo)["sid"]
    assert await _sesion_revocada(session_factory, sid)
    assert (await https.post("/api/auth/refresh", headers=CSRF)).status_code == 401
    assert (await https.get("/api/auth/me", headers={"Authorization": f"Bearer {rotado.json()['access_token']}"})
            ).status_code == 401


async def test_logout_sin_cookie_o_con_cookie_basura_igual_es_200_y_revoca_la_sesion_del_access(
        https, usuario, session_factory) -> None:
    login = await _login(https)
    sid = decode_token(login.json()["access_token"])["sid"]
    https.cookies.clear()
    https.cookies.set("refresh_token", "no-es-un-jwt", domain="test", path="/api/auth")
    r = await https.post("/api/auth/logout", headers={"Authorization": f"Bearer {login.json()['access_token']}"})
    assert r.status_code == 200 and _borrada(r)
    assert await _sesion_revocada(session_factory, sid)


async def test_logout_deja_auditoria(https, usuario, session_factory) -> None:
    login = await _login(https)
    await https.post("/api/auth/logout", headers={"Authorization": f"Bearer {login.json()['access_token']}"})
    async with session_factory() as s:
        n = (await s.execute(select(func.count()).select_from(RegistroAuditoria)
                             .where(RegistroAuditoria.accion == "LOGOUT"))).scalar_one()
    assert n == 1
