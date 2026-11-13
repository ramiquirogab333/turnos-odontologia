"""C-13 (O17): LOGIN_FAILED nunca guarda el email intentado. Datos sintéticos (R19)."""

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.models.core import RegistroAuditoria
from tests.conftest import PASSWORD_PANEL, crear_usuario_panel

EMAIL = "recepcion@turnos.test"
INEXISTENTE = "nadie.existe@turnos.test"


def _cliente() -> AsyncClient:
    from app.main import app

    return AsyncClient(transport=ASGITransport(app=app, client=("198.51.100.30", 4000)), base_url="https://test")


async def _todos(factory) -> list[RegistroAuditoria]:  # type: ignore[no-untyped-def]
    async with factory() as s:
        return list((await s.execute(select(RegistroAuditoria).order_by(RegistroAuditoria.id))).scalars())


def _texto(r: RegistroAuditoria) -> str:
    return " ".join(str(v) for v in (r.usuario_id, r.accion, r.entidad, r.entidad_id, r.datos_antes, r.datos_despues, r.ip))


async def test_un_email_inexistente_deja_login_failed_con_entidad_id_nulo_y_sin_el_email(session_factory) -> None:  # type: ignore[no-untyped-def]
    async with _cliente() as c:
        r = await c.post("/api/auth/login", json={"email": INEXISTENTE, "password": "equivocada-123"})
    assert r.status_code == 401
    [fila] = [x for x in await _todos(session_factory) if x.accion == "LOGIN_FAILED"]
    assert (fila.entidad_id, fila.usuario_id, fila.ip) == (None, None, "198.51.100.30")
    assert fila.datos_despues == {"motivo": "credenciales"}
    assert INEXISTENTE not in _texto(fila) and "nadie" not in _texto(fila)


async def test_un_usuario_existente_con_clave_mala_conserva_su_id_y_no_guarda_el_email(session_factory) -> None:  # type: ignore[no-untyped-def]
    uid, _ = await crear_usuario_panel(session_factory, EMAIL, ["recepcion"])
    async with _cliente() as c:
        assert (await c.post("/api/auth/login", json={"email": EMAIL, "password": "equivocada-123"})).status_code == 401
    [fila] = [x for x in await _todos(session_factory) if x.accion == "LOGIN_FAILED"]
    assert (fila.entidad_id, fila.usuario_id) == (str(uid), uid)
    assert EMAIL not in _texto(fila)


async def test_el_bloqueo_y_el_limite_siguen_sin_depender_del_email_auditado(session_factory) -> None:  # type: ignore[no-untyped-def]
    async with _cliente() as c:
        estados = [(await c.post("/api/auth/login", json={"email": INEXISTENTE, "password": "equivocada-123"})).status_code
                   for _ in range(7)]
    assert estados[:5] == [401] * 5 and estados[5:] == [429, 429]
    todos = await _todos(session_factory)
    assert sum(1 for x in todos if x.accion == "LOGIN_FAILED") == 5
    bloqueos = [x for x in todos if x.accion == "LOGIN_BLOQUEADO"]
    assert len(bloqueos) >= 1 and all(b.entidad_id is None for b in bloqueos)
    assert all(INEXISTENTE not in _texto(x) for x in todos)
    # Con otro email el contador por IP+email es independiente y sigue respondiendo 401 (no 429).
    async with _cliente() as c:
        assert (await c.post("/api/auth/login", json={"email": "otra.persona@turnos.test", "password": PASSWORD_PANEL})
                ).status_code == 401
