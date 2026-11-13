"""C-08 (9.1, O4): comando idempotente que crea usuarios del panel. PostgreSQL real. Datos 100 % sintéticos (R19)."""

import pytest
from sqlalchemy import func, select

from app.models.core import Rol, Usuario, UsuarioRol
from app.panel.usuarios import ejecutar
from tests.panel_helpers import sembrar_mundo

CLAVE = "clave-sintetica-del-panel-2031"


@pytest.fixture
async def mundo(session_factory, clean_db):
    return await sembrar_mundo(session_factory)


def _args(email: str = "recepcion@turnos.test", rol: str = "recepcion", *extra: str) -> list[str]:
    return ["--email", email, "--nombre", "Rita Recepción", "--rol", rol, *extra]


async def _usuarios(session_factory) -> list[Usuario]:
    async with session_factory() as s:
        return list((await s.execute(select(Usuario).order_by(Usuario.id))).scalars().all())


async def _roles_de(session_factory, email: str) -> list[str]:
    async with session_factory() as s:
        return list((await s.execute(
            select(Rol.nombre).join(UsuarioRol, UsuarioRol.rol_id == Rol.id).join(Usuario, Usuario.id == UsuarioRol.usuario_id)
            .where(Usuario.email == email))).scalars().all())


async def test_crea_recepcion_con_su_rol_y_puede_ingresar_con_la_contrasena_del_entorno(
        client, mundo, session_factory) -> None:
    assert await ejecutar(_args(), {"PANEL_USUARIO_PASSWORD": CLAVE}) == 0
    (u,) = await _usuarios(session_factory)
    assert (u.email, u.nombre_completo, u.is_active, u.profesional_id) == ("recepcion@turnos.test", "Rita Recepción", True, None)
    assert u.hashed_password != CLAVE and u.hashed_password.startswith("$2")
    assert await _roles_de(session_factory, u.email) == ["recepcion"]
    login = await client.post("/api/auth/login", json={"email": "recepcion@turnos.test", "password": CLAVE})
    assert login.status_code == 200, login.text


async def test_odontologo_con_profesional_queda_asociado_a_su_agenda(client, mundo, session_factory) -> None:
    args = _args("dra.ficticia@turnos.test", "odontologo", "--profesional-id", str(mundo["ana"]))
    assert await ejecutar(args, {"PANEL_USUARIO_PASSWORD": CLAVE}) == 0
    (u,) = await _usuarios(session_factory)
    assert u.profesional_id == mundo["ana"] and await _roles_de(session_factory, u.email) == ["odontologo"]


async def test_sin_contrasena_en_el_entorno_falla_y_no_crea_nada(mundo, session_factory, capsys) -> None:
    assert await ejecutar(_args(), {}) != 0
    assert await ejecutar(_args(), {"PANEL_USUARIO_PASSWORD": ""}) != 0
    assert await _usuarios(session_factory) == []
    assert "PANEL_USUARIO_PASSWORD" in capsys.readouterr().err


@pytest.mark.parametrize("args,motivo", [
    (_args(rol="superusuario"), "rol"),
    (_args("dra@turnos.test", "odontologo"), "profesional"),                 # odontólogo sin profesional
    (_args("dra@turnos.test", "odontologo", "--profesional-id", "999999"), "profesional"),  # profesional inexistente
    (_args("sin-arroba"), "email"),
])
async def test_entradas_invalidas_fallan_con_un_motivo_y_no_crean_nada(mundo, session_factory, capsys, args, motivo) -> None:
    assert await ejecutar(args, {"PANEL_USUARIO_PASSWORD": CLAVE}) != 0
    assert await _usuarios(session_factory) == []
    assert motivo in capsys.readouterr().err.lower()


async def test_una_contrasena_corta_falla(mundo, session_factory) -> None:
    assert await ejecutar(_args(), {"PANEL_USUARIO_PASSWORD": "corta"}) != 0
    assert await _usuarios(session_factory) == []


async def test_la_contrasena_no_se_imprime_ni_se_registra_en_logs(mundo, capsys, caplog) -> None:
    caplog.set_level("DEBUG")
    assert await ejecutar(_args(), {"PANEL_USUARIO_PASSWORD": CLAVE}) == 0
    assert await ejecutar(_args("otra@turnos.test", "recepcion"), {"PANEL_USUARIO_PASSWORD": "corta"}) != 0
    salida = capsys.readouterr()
    for texto in (salida.out, salida.err, caplog.text):
        assert CLAVE not in texto and "corta" not in texto.replace("contraseña corta", "")


async def test_doble_corrida_no_duplica_usuario_ni_rol_y_actualiza_los_datos(client, mundo, session_factory) -> None:
    assert await ejecutar(_args(), {"PANEL_USUARIO_PASSWORD": CLAVE}) == 0
    nueva = "otra-clave-sintetica-2032"
    args = ["--email", "recepcion@turnos.test", "--nombre", "Rita R. Recepción", "--rol", "recepcion"]
    assert await ejecutar(args, {"PANEL_USUARIO_PASSWORD": nueva}) == 0
    (u,) = await _usuarios(session_factory)
    assert u.nombre_completo == "Rita R. Recepción"
    assert await _roles_de(session_factory, u.email) == ["recepcion"]
    async with session_factory() as s:
        assert (await s.execute(select(func.count()).select_from(UsuarioRol))).scalar_one() == 1
    assert (await client.post("/api/auth/login", json={"email": u.email, "password": nueva})).status_code == 200
    assert (await client.post("/api/auth/login", json={"email": u.email, "password": CLAVE})).status_code == 401


async def test_un_segundo_rol_se_suma_sin_quitar_el_primero(mundo, session_factory) -> None:
    assert await ejecutar(_args(), {"PANEL_USUARIO_PASSWORD": CLAVE}) == 0
    assert await ejecutar(_args("recepcion@turnos.test", "admin"), {"PANEL_USUARIO_PASSWORD": CLAVE}) == 0
    assert sorted(await _roles_de(session_factory, "recepcion@turnos.test")) == ["admin", "recepcion"]
    assert len(await _usuarios(session_factory)) == 1


# --- C-15 (8.1, D9, O13): desactivar y reactivar ---------------------------------------------------------------

DRA = "dra.ficticia@turnos.test"


async def _alta_dra(mundo) -> None:
    assert await ejecutar(["--email", DRA, "--nombre", "Ana Ficticia", "--rol", "odontologo", "--profesional-id",
                           str(mundo["ana"])], {"PANEL_USUARIO_PASSWORD": CLAVE}) == 0


async def _dos_sesiones(client, mundo) -> tuple[list[str], list[str]]:
    accesos, cookies = [], []
    for _ in range(2):
        r = await client.post("/api/auth/login", json={"email": DRA, "password": CLAVE})
        assert r.status_code == 200, r.text
        accesos.append(r.json()["access_token"])
        cookies.append(next(h for h in r.headers.get_list("set-cookie") if h.startswith("refresh_token=")
                            ).split(";", 1)[0].split("=", 1)[1])
    return accesos, cookies


async def test_desactivar_deja_inactivo_revoca_las_dos_sesiones_y_audita_la_cantidad(
        client, mundo, session_factory) -> None:
    from app.models.auth import SesionPanel
    from app.models.core import RegistroAuditoria

    await _alta_dra(mundo)
    accesos, _ = await _dos_sesiones(client, mundo)
    assert await ejecutar(["--email", DRA, "--desactivar"], {}) == 0  # sin pedir contraseña
    (u,) = await _usuarios(session_factory)
    assert u.is_active is False
    async with session_factory() as s:
        sesiones = list((await s.execute(select(SesionPanel))).scalars())
        auditoria = list((await s.execute(select(RegistroAuditoria).where(
            RegistroAuditoria.accion == "SESIONES_REVOCADAS"))).scalars())
    assert len(sesiones) == 2 and all(x.motivo_revocacion == "usuario_desactivado" and x.revocada_en for x in sesiones)
    assert [a.datos_despues for a in auditoria] == [{"cantidad": 2}]
    for token in accesos:
        assert (await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})).status_code == 401


async def test_desactivar_un_email_inexistente_falla_explica_y_no_cambia_nada(mundo, session_factory, capsys) -> None:
    await _alta_dra(mundo)
    assert await ejecutar(["--email", "nadie@turnos.test", "--desactivar"], {}) == 1
    assert "nadie@turnos.test" in capsys.readouterr().err
    (u,) = await _usuarios(session_factory)
    assert u.is_active is True


async def test_reactivar_no_revive_sesiones_pero_permite_ingresar_de_nuevo(client, mundo, session_factory) -> None:
    await _alta_dra(mundo)
    _, cookies = await _dos_sesiones(client, mundo)
    assert await ejecutar(["--email", DRA, "--desactivar"], {}) == 0
    assert await ejecutar(["--email", DRA, "--reactivar"], {}) == 0
    (u,) = await _usuarios(session_factory)
    assert u.is_active is True
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as https:
        https.cookies.set("refresh_token", cookies[0], domain="test", path="/api/auth")
        viejo = await https.post("/api/auth/refresh", headers={"X-Panel-Csrf": "1"})
        assert viejo.status_code == 401
        assert (await https.post("/api/auth/login", json={"email": DRA, "password": CLAVE})).status_code == 200


async def test_el_alta_sobre_un_usuario_desactivado_actualiza_la_contrasena_sigue_inactivo_y_avisa(
        client, mundo, session_factory, capsys) -> None:
    await _alta_dra(mundo)
    assert await ejecutar(["--email", DRA, "--desactivar"], {}) == 0
    capsys.readouterr()
    nueva = "otra-clave-sintetica-2031"
    assert await ejecutar(["--email", DRA, "--nombre", "Ana Ficticia", "--rol", "odontologo", "--profesional-id",
                           str(mundo["ana"])], {"PANEL_USUARIO_PASSWORD": nueva}) == 0
    (u,) = await _usuarios(session_factory)
    assert u.is_active is False
    assert "desactivado" in capsys.readouterr().err
    assert (await client.post("/api/auth/login", json={"email": DRA, "password": nueva})).status_code == 401


@pytest.mark.parametrize("extra", [["--rol", "recepcion"], ["--nombre", "Otra Persona"], ["--reactivar"]])
async def test_desactivar_junto_con_otras_opciones_es_error_de_uso(mundo, session_factory, extra, capsys) -> None:
    await _alta_dra(mundo)
    assert await ejecutar(["--email", DRA, "--desactivar", *extra], {}) != 0
    (u,) = await _usuarios(session_factory)
    assert u.is_active is True


async def test_desactivar_es_idempotente_y_cuenta_cero_la_segunda_vez(client, mundo, session_factory) -> None:
    from app.models.core import RegistroAuditoria

    await _alta_dra(mundo)
    await _dos_sesiones(client, mundo)
    assert await ejecutar(["--email", DRA, "--desactivar"], {}) == 0
    assert await ejecutar(["--email", DRA, "--desactivar"], {}) == 0
    async with session_factory() as s:
        cantidades = sorted(a.datos_despues["cantidad"] for a in (await s.execute(select(RegistroAuditoria).where(
            RegistroAuditoria.accion == "SESIONES_REVOCADAS"))).scalars())
    assert cantidades == [0, 2]
