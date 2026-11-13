"""C-15 (7.1-7.5): límites aplicados al login, al refresh y a lo público. Datos sintéticos (R19): IPs de documentación."""

import asyncio
import logging
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import func, select

from app.models.auth import SesionPanel
from app.models.core import RegistroAuditoria
from app.shared.limites import LimitadorEnMemoria, LimitadorTolerante, Resultado, get_limitador_base
from tests.conftest import PASSWORD_PANEL, crear_usuario_panel, future_iso

EMAIL = "recepcion@turnos.test"
CSRF = {"X-Panel-Csrf": "1"}
MALA = "contrasena-equivocada-1"


def _cliente(ip: str = "198.51.100.10") -> AsyncClient:
    from app.main import app

    return AsyncClient(transport=ASGITransport(app=app, client=(ip, 4000)), base_url="https://test")


@pytest_asyncio.fixture
async def https() -> AsyncIterator[AsyncClient]:
    async with _cliente() as c:
        yield c


async def _login(c: AsyncClient, email: str = EMAIL, password: str = PASSWORD_PANEL) -> Response:
    return await c.post("/api/auth/login", json={"email": email, "password": password})


async def _sesiones(factory) -> int:
    async with factory() as s:
        return (await s.execute(select(func.count()).select_from(SesionPanel))).scalar_one()


async def _bloqueos(factory) -> list[RegistroAuditoria]:
    async with factory() as s:
        return list((await s.execute(select(RegistroAuditoria).where(RegistroAuditoria.accion == "LOGIN_BLOQUEADO"))
                     ).scalars())


# --- 7.1 login ---------------------------------------------------------------------------------------------------

async def test_cuatro_fallos_y_un_exito_reinician_el_par(https, session_factory) -> None:
    await crear_usuario_panel(session_factory, EMAIL, ["recepcion"])
    for _ in range(4):
        assert (await _login(https, password=MALA)).status_code == 401
    assert (await _login(https)).status_code == 200  # el quinto intento, correcto, todavía entra
    for _ in range(4):  # el éxito reinició el par: otros cuatro fallos tampoco bloquean
        assert (await _login(https, password=MALA)).status_code == 401
    assert (await _login(https)).status_code == 200


async def test_el_sexto_intento_es_429_sin_verificar_la_contrasena_ni_crear_sesion(
        https, session_factory, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.auth import router as router_auth

    await crear_usuario_panel(session_factory, EMAIL, ["recepcion"])
    for _ in range(5):
        assert (await _login(https, password=MALA)).status_code == 401
    verificaciones: list[str] = []
    real = router_auth.verify_password
    monkeypatch.setattr(router_auth, "verify_password", lambda p, h: verificaciones.append(h) or real(p, h))
    antes = await _sesiones(session_factory)
    r = await _login(https)  # aun con la contraseña correcta
    assert r.status_code == 429
    assert verificaciones == []
    assert await _sesiones(session_factory) == antes
    assert int(r.headers["Retry-After"]) >= 1
    assert r.json()["motivo"] == "demasiados_intentos"
    assert not any(h.startswith("refresh_token=") for h in r.headers.get_list("set-cookie"))


async def test_otra_ip_con_el_mismo_email_entra(https, session_factory) -> None:
    await crear_usuario_panel(session_factory, EMAIL, ["recepcion"])
    for _ in range(5):
        await _login(https, password=MALA)
    assert (await _login(https)).status_code == 429
    async with _cliente("203.0.113.9") as otra:
        assert (await _login(otra)).status_code == 200


async def test_el_429_no_revela_si_el_email_existe(https, session_factory) -> None:
    await crear_usuario_panel(session_factory, EMAIL, ["recepcion"])
    cuerpos = []
    for email in (EMAIL, "inexistente@turnos.test"):
        for _ in range(5):
            await _login(https, email=email, password=MALA)
        r = await _login(https, email=email, password=MALA)
        assert r.status_code == 429
        cuerpos.append((r.json(), r.headers["Retry-After"] is not None))
    assert cuerpos[0] == cuerpos[1]


async def test_mayusculas_y_espacios_cuentan_como_el_mismo_email(https, session_factory) -> None:
    await crear_usuario_panel(session_factory, EMAIL, ["recepcion"])
    variantes = [EMAIL, EMAIL.upper(), f"  {EMAIL} ", "Recepcion@Turnos.test", EMAIL]
    for variante in variantes:
        assert (await _login(https, email=variante, password=MALA)).status_code == 401
    assert (await _login(https, email=" RECEPCION@turnos.test ")).status_code == 429


async def test_login_bloqueado_se_audita_una_sola_vez_por_clave_y_ventana(https, session_factory) -> None:
    await crear_usuario_panel(session_factory, EMAIL, ["recepcion"])
    for _ in range(5):
        await _login(https, password=MALA)
    for _ in range(30):
        assert (await _login(https, password=MALA)).status_code == 429
    registros = await _bloqueos(session_factory)
    par = [r for r in registros if r.datos_despues == {"limite": "ipemail"}]
    assert len(par) == 1 and par[0].ip == "198.51.100.10"
    assert par[0].entidad_id is None and par[0].usuario_id is None  # no se guarda el email, ni en claro
    assert all(EMAIL not in str(r.datos_despues) for r in registros)
    assert len(registros) <= 2  # a lo sumo el par y, por tope de intentos, la IP: nunca uno por intento rechazado


# --- 7.3 refresh -------------------------------------------------------------------------------------------------

async def test_sesenta_renovaciones_pasan_y_la_61_es_429_con_la_cookie_y_la_sesion_intactas(
        https, session_factory) -> None:
    await crear_usuario_panel(session_factory, EMAIL, ["recepcion"])
    login = await _login(https)
    assert login.status_code == 200
    ultimo = login
    for _ in range(60):
        ultimo = await https.post("/api/auth/refresh", headers=CSRF)
        assert ultimo.status_code == 200
    r = await https.post("/api/auth/refresh", headers=CSRF)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
    assert not any(h.startswith("refresh_token=") for h in r.headers.get_list("set-cookie"))  # la cookie no se toca
    me = await https.get("/api/auth/me", headers={"Authorization": f"Bearer {ultimo.json()['access_token']}"})
    assert me.status_code == 200  # la sesión sigue válida


async def test_sin_la_cabecera_csrf_es_403_y_cuenta_para_el_limite(https, session_factory) -> None:
    await crear_usuario_panel(session_factory, EMAIL, ["recepcion"])
    await _login(https)
    for _ in range(60):
        assert (await https.post("/api/auth/refresh")).status_code == 403
    assert (await https.post("/api/auth/refresh", headers=CSRF)).status_code == 429


# --- 7.4 lo público ----------------------------------------------------------------------------------------------

async def test_quince_lecturas_y_una_escritura_no_dan_429(https) -> None:
    for _ in range(15):
        assert (await https.get("/api/public/tratamientos")).status_code == 200
    r = await https.post("/api/public/gestion/cancelar", headers={"X-Codigo-Gestion": "00000000-0000-4000-8000-000000000000"})
    assert r.status_code != 429


async def test_la_escritura_numero_11_es_429_y_no_crea_turno(https, seed_ids, session_factory) -> None:
    from app.turnos.models import Turno

    cuerpo = {"nombre": "Paciente Ficticio", "telefono": "+5491100000001",
              "tratamiento_id": seed_ids["tratamiento_id"], "profesional_id": seed_ids["profesional_id"],
              "inicio": future_iso(180)}
    for _ in range(10):
        assert (await https.post("/api/public/turnos", json={**cuerpo, "telefono": "x"})).status_code != 429  # 422
    r = await https.post("/api/public/turnos", json=cuerpo)
    assert r.status_code == 429 and r.json()["motivo"] == "demasiados_intentos"
    async with session_factory() as s:
        assert (await s.execute(select(func.count()).select_from(Turno))).scalar_one() == 0


async def test_los_limites_de_lectura_y_escritura_son_independientes(https) -> None:
    for _ in range(10):
        await https.post("/api/public/gestion/cancelar", headers={"X-Codigo-Gestion": "00000000-0000-4000-8000-000000000000"})
    assert (await https.post("/api/public/gestion/cancelar", headers={"X-Codigo-Gestion": "x"})).status_code == 429
    assert (await https.get("/api/public/tratamientos")).status_code == 200  # la lectura tiene su propio cupo


async def test_los_webhooks_y_la_salud_no_tienen_limite(https) -> None:
    for _ in range(200):
        r = await https.post("/api/webhooks/mercadopago", json={})
        assert r.status_code != 429
    for _ in range(130):
        assert (await https.get("/api/health")).status_code == 200


async def test_distintas_ip_publicas_tienen_su_propio_cupo(https) -> None:
    for _ in range(10):
        await https.post("/api/public/gestion/cancelar", headers={"X-Codigo-Gestion": "x"})
    assert (await https.post("/api/public/gestion/cancelar", headers={"X-Codigo-Gestion": "x"})).status_code == 429
    async with _cliente("192.0.2.77") as otra:
        assert (await otra.post("/api/public/gestion/cancelar", headers={"X-Codigo-Gestion": "x"})).status_code != 429


# --- 7.5 el almacén de contadores cae --------------------------------------------------------------------------

class AlmacenCaido:
    async def consumir(self, clave: str, maximo: int, ventana_segundos: int) -> Resultado:
        raise ConnectionError("redis caído")

    async def registrar(self, clave: str, ventana_segundos: int) -> None:
        raise ConnectionError("redis caído")

    async def consultar(self, clave: str, maximo: int) -> Resultado:
        raise ConnectionError("redis caído")

    async def reiniciar(self, clave: str) -> None:
        raise ConnectionError("redis caído")


class AlmacenLento(AlmacenCaido):
    async def consumir(self, clave: str, maximo: int, ventana_segundos: int) -> Resultado:
        await asyncio.sleep(5)
        return Resultado(False, 99)

    async def consultar(self, clave: str, maximo: int) -> Resultado:
        await asyncio.sleep(5)
        return Resultado(False, 99)


@pytest.mark.parametrize("almacen", [AlmacenCaido, AlmacenLento])
async def test_sin_el_almacen_la_api_sigue_atendiendo_y_el_aviso_no_lleva_email_ni_ip(
        almacen, https, session_factory, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    from app.main import app

    monkeypatch.setenv("RATE_LIMIT_TIMEOUT_MS", "20")
    await crear_usuario_panel(session_factory, EMAIL, ["recepcion"])
    app.dependency_overrides[get_limitador_base] = lambda: almacen()
    caplog.set_level(logging.WARNING)
    assert (await _login(https)).status_code == 200
    assert (await https.get("/api/public/tratamientos")).status_code == 200
    avisos = [r.getMessage() for r in caplog.records if "limite no aplicado" in r.getMessage()]
    assert len(avisos) == 1  # a lo sumo uno por minuto
    assert EMAIL not in avisos[0] and "198.51.100.10" not in avisos[0] and "recepcion" not in avisos[0]


async def test_un_limitador_tolerante_con_almacen_sano_aplica_el_limite(limitador: LimitadorEnMemoria) -> None:
    tolerante = LimitadorTolerante(limitador, timeout_ms=50)
    assert (await tolerante.consumir("rl:v1:t", 1, 60)).permitido
    assert not (await tolerante.consumir("rl:v1:t", 1, 60)).permitido
