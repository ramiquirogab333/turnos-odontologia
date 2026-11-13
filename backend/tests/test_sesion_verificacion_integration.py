"""C-15 (3.4-3.6): cada pedido verifica la sesión; máximo absoluto con reloj inyectado. Datos sintéticos (R19)."""

import asyncio
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt
import pytest_asyncio
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import delete, event, select, update

from app.auth.service import create_access_token
from app.models.auth import SesionPanel
from app.models.core import Rol, Usuario, UsuarioRol
from app.shared.db import get_engine
from app.shared.settings import get_settings
from tests.conftest import PASSWORD_PANEL, crear_sesion_sintetica, crear_usuario_panel

EMAIL = "recepcion@turnos.test"
CSRF = {"X-Panel-Csrf": "1"}
AGENDA = "/api/panel/agenda"
PARAMS = {"vista": "dia", "fecha": "2031-06-02"}


@pytest_asyncio.fixture
async def https() -> AsyncIterator[AsyncClient]:
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as ac:
        yield ac


def _cab(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _login(c: AsyncClient, email: str = EMAIL) -> Response:
    return await c.post("/api/auth/login", json={"email": email, "password": PASSWORD_PANEL})


def _claims(token: str) -> dict[str, object]:
    ajustes = get_settings()
    return jwt.decode(token, ajustes.jwt_secret_key, algorithms=[ajustes.jwt_algorithm],
                      options={"verify_exp": False, "verify_iat": False})


def _cookie(r: Response) -> str:
    return next(h for h in r.headers.get_list("set-cookie") if h.startswith("refresh_token="))


def _borrada(r: Response) -> bool:
    c = _cookie(r).lower()
    return "max-age=0" in c or "1970" in c


# --- 3.4 verificación por pedido ---------------------------------------------------------------------------------

async def test_pedido_con_sesion_vigente_es_200(https, session_factory) -> None:
    _, token = await crear_usuario_panel(session_factory, EMAIL, ["recepcion"])
    assert (await https.get(AGENDA, params=PARAMS, headers=_cab(token))).status_code == 200


async def test_access_de_una_sesion_cerrada_es_401_aunque_el_jwt_siga_vigente(https, session_factory) -> None:
    uid, token = await crear_usuario_panel(session_factory, EMAIL, ["recepcion"])
    assert (await https.get(AGENDA, params=PARAMS, headers=_cab(token))).status_code == 200
    sid = _claims(token)["sid"]
    async with session_factory() as s:
        await s.execute(update(SesionPanel).where(SesionPanel.sid == UUID(str(sid))).values(
            revocada_en=datetime.now(timezone.utc) - timedelta(minutes=1), motivo_revocacion="logout"))
        await s.commit()
    r = await https.get(AGENDA, params=PARAMS, headers=_cab(token))
    assert r.status_code == 401
    assert "dias" not in r.text and "turnos" not in r.text  # no devuelve ningún dato


async def test_rol_quitado_con_la_sesion_abierta_da_403_en_la_caja(https, session_factory) -> None:
    from app.turnos.models import Profesional

    async with session_factory() as s:
        profesional = Profesional(nombre="Rita Ficticia", matricula="MP-0001", especialidad="General")
        s.add(profesional)
        await s.commit()
        profesional_id = int(profesional.id)
    uid, token = await crear_usuario_panel(session_factory, "rita.ficticia@turnos.test", ["recepcion", "odontologo"],
                                           profesional_id=profesional_id)
    caja = {"dia": "2031-06-02"}
    assert (await https.get("/api/panel/caja", params=caja, headers=_cab(token))).status_code == 200
    async with session_factory() as s:
        rol = (await s.execute(select(Rol).where(Rol.nombre == "recepcion"))).scalar_one()
        await s.execute(delete(UsuarioRol).where(UsuarioRol.usuario_id == uid, UsuarioRol.rol_id == rol.id))
        await s.commit()
    # el access sigue emitido con ambos roles, pero los permisos salen de la base
    assert "recepcion" in _claims(token)["roles"]
    assert (await https.get("/api/panel/caja", params=caja, headers=_cab(token))).status_code == 403


async def test_usuario_inactivo_con_sesion_abierta_es_401(https, session_factory) -> None:
    uid, token = await crear_usuario_panel(session_factory, EMAIL, ["recepcion"])
    async with session_factory() as s:
        await s.execute(update(Usuario).where(Usuario.id == uid).values(is_active=False))
        await s.commit()
    assert (await https.get(AGENDA, params=PARAMS, headers=_cab(token))).status_code == 401


async def test_token_sin_sid_es_401(https, session_factory) -> None:
    uid, _ = await crear_usuario_panel(session_factory, EMAIL, ["recepcion"])
    sin_sid = create_access_token({"sub": str(uid), "roles": ["recepcion"], "email": EMAIL, "jti": str(uuid4())})
    assert (await https.get(AGENDA, params=PARAMS, headers=_cab(sin_sid))).status_code == 401


async def test_token_con_sid_inexistente_es_401(https, session_factory) -> None:
    uid, _ = await crear_usuario_panel(session_factory, EMAIL, ["recepcion"])
    huerfano = create_access_token({"sub": str(uid), "roles": ["recepcion"], "email": EMAIL, "jti": str(uuid4()),
                                    "sid": str(uuid4())})
    assert (await https.get(AGENDA, params=PARAMS, headers=_cab(huerfano))).status_code == 401


async def test_token_con_sid_que_no_es_uuid_es_401_no_500(https, session_factory) -> None:
    uid, _ = await crear_usuario_panel(session_factory, EMAIL, ["recepcion"])
    raro = create_access_token({"sub": str(uid), "roles": ["recepcion"], "email": EMAIL, "jti": str(uuid4()),
                                "sid": "no-es-un-uuid"})
    assert (await https.get(AGENDA, params=PARAMS, headers=_cab(raro))).status_code == 401


async def test_un_sid_de_otro_usuario_no_sirve(https, session_factory) -> None:
    _, token_a = await crear_usuario_panel(session_factory, EMAIL, ["recepcion"])
    uid_b, _ = await crear_usuario_panel(session_factory, "admin@turnos.test", ["admin"])
    sid_a = str(_claims(token_a)["sid"])
    cruzado = create_access_token({"sub": str(uid_b), "roles": ["admin"], "email": "admin@turnos.test",
                                   "jti": str(uuid4()), "sid": sid_a})
    assert (await https.get(AGENDA, params=PARAMS, headers=_cab(cruzado))).status_code == 401


async def test_una_sola_sentencia_sql_por_pedido_autenticado(https, session_factory) -> None:
    _, token = await crear_usuario_panel(session_factory, EMAIL, ["recepcion"])
    sentencias: list[str] = []
    motor = get_engine().sync_engine

    def contar(conn, cursor, statement, parameters, context, executemany) -> None:  # noqa: ANN001
        sentencias.append(statement)

    event.listen(motor, "before_cursor_execute", contar)
    try:
        r = await https.get("/api/panel/agenda/opciones", headers=_cab(token))
    finally:
        event.remove(motor, "before_cursor_execute", contar)
    assert r.status_code == 200
    de_sesion = [q for q in sentencias if "sesion_panel" in q]
    assert len(de_sesion) == 1, de_sesion
    assert "usuario_rol" in de_sesion[0]  # sesión + usuario + roles en la misma consulta


# --- 3.6 máximo absoluto con reloj inyectado -------------------------------------------------------------------

async def _sesion_de_login(https: AsyncClient, session_factory) -> tuple[str, datetime, datetime]:
    """Login real a las ``ahora``; devuelve (cookie de refresh, creada_en, expira_en) de la sesión."""
    r = await _login(https)
    assert r.status_code == 200, r.text
    sid = UUID(str(_claims(r.json()["access_token"])["sid"]))
    async with session_factory() as s:
        fila = (await s.execute(select(SesionPanel).where(SesionPanel.sid == sid))).scalar_one()
    return r.headers.get_list("set-cookie")[0], fila.creada_en, fila.expira_en


async def test_renovar_dentro_del_maximo_acota_los_vencimientos_al_tope(
        https, session_factory, reloj: Callable[[datetime], None]) -> None:
    await crear_usuario_panel(session_factory, EMAIL, ["recepcion"])
    _, creada, tope = await _sesion_de_login(https, session_factory)
    assert tope - creada == timedelta(hours=get_settings().sesion_maxima_horas)
    reloj(tope - timedelta(minutes=10))  # "19:50" de una sesión que vence a las 20:00
    r = await https.post("/api/auth/refresh", headers=CSRF)
    assert r.status_code == 200, r.text
    assert _claims(r.json()["access_token"])["exp"] <= int(tope.timestamp())
    refresh = _cookie(r).split(";", 1)[0].split("=", 1)[1]
    assert _claims(refresh)["exp"] <= int(tope.timestamp())


async def test_renovar_pasado_el_maximo_es_401_y_borra_la_cookie(
        https, session_factory, reloj: Callable[[datetime], None]) -> None:
    await crear_usuario_panel(session_factory, EMAIL, ["recepcion"])
    _, _, tope = await _sesion_de_login(https, session_factory)
    reloj(tope + timedelta(minutes=1))  # "20:01"
    r = await https.post("/api/auth/refresh", headers=CSRF)
    assert r.status_code == 401 and _borrada(r)
    assert "access_token" not in r.text


async def test_en_el_instante_exacto_del_vencimiento_es_401_porque_es_exclusivo(
        https, session_factory, reloj: Callable[[datetime], None]) -> None:
    await crear_usuario_panel(session_factory, EMAIL, ["recepcion"])
    _, _, tope = await _sesion_de_login(https, session_factory)
    reloj(tope)  # "20:00:00"
    r = await https.post("/api/auth/refresh", headers=CSRF)
    assert r.status_code == 401 and _borrada(r)


async def test_el_access_de_una_sesion_vencida_es_401(
        https, session_factory, reloj: Callable[[datetime], None]) -> None:
    uid, _ = await crear_usuario_panel(session_factory, EMAIL, ["recepcion"])
    ahora = datetime.now(timezone.utc)
    _, access, _ = await crear_sesion_sintetica(session_factory, uid, EMAIL, ["recepcion"], creada_en=ahora,
                                                expira_en=ahora + timedelta(minutes=5))
    assert (await https.get(AGENDA, params=PARAMS, headers=_cab(access))).status_code == 200
    reloj(ahora + timedelta(minutes=5))  # exacto: exclusivo
    assert (await https.get(AGENDA, params=PARAMS, headers=_cab(access))).status_code == 401


async def test_dos_pedidos_simultaneos_con_la_misma_sesion_no_chocan(https, session_factory) -> None:
    _, token = await crear_usuario_panel(session_factory, EMAIL, ["recepcion"])
    resultados = await asyncio.gather(*[https.get(AGENDA, params=PARAMS, headers=_cab(token)) for _ in range(5)])
    assert [r.status_code for r in resultados] == [200] * 5
