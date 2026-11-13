"""C-10 (5.1-5.5): conexión OAuth, callback, desconexión y estado según el rol. Sintético (R19), sin red."""

import base64
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integraciones.gcal.cifrado import descifrar
from app.integraciones.gcal.deps import get_proveedor
from app.integraciones.gcal.proveedor_falso import ProveedorFalso
from app.integraciones.gcal.proveedor_http import ProveedorHttp
from app.models.core import RegistroAuditoria
from tests.conftest import bearer, crear_usuario_panel
from tests.gcal_helpers import AHORA, CLAVE_FERNET, conexion, conflictos, eventos, sembrar_conexion
from tests.panel_helpers import insertar_turno, sembrar_mundo

Factory = async_sessionmaker[AsyncSession]
BASE = "/api/panel/google-calendar"


async def _odontologa(factory: Factory, mundo: dict[str, int], clave: str = "ana", email: str = "ana.prueba@example.com"
                      ) -> tuple[int, str]:
    return await crear_usuario_panel(factory, email, ["odontologo"], profesional_id=mundo[clave])


def _state(url: str) -> str:
    return parse_qs(urlparse(url).query)["state"][0]


# --- 5.1 Iniciar -------------------------------------------------------------------------------------------------

async def test_iniciar_devuelve_la_url_de_google_y_deja_la_conexion_pendiente(
        client: AsyncClient, session_factory: Factory, proveedor_gcal: ProveedorFalso, reloj) -> None:
    reloj(AHORA)
    mundo = await sembrar_mundo(session_factory)
    usuario, token = await _odontologa(session_factory, mundo)
    respuesta = await client.post(f"{BASE}/conexion/iniciar", headers=bearer(token))
    assert respuesta.status_code == 200
    url = respuesta.json()["url_autorizacion"]
    consulta = parse_qs(urlparse(url).query)
    assert urlparse(url).netloc == "accounts.google.com" and urlparse(url).path == "/o/oauth2/v2/auth"
    assert consulta["scope"] == ["https://www.googleapis.com/auth/calendar.events openid email"]
    assert consulta["code_challenge_method"] == ["S256"] and consulta["access_type"] == ["offline"]
    assert consulta["client_id"] == ["cliente-sintetico.apps.googleusercontent.com"] and consulta["state"]
    fila = await conexion(session_factory, (await _conexion_de(session_factory, mundo["ana"])).id)
    assert (fila.estado, fila.usuario_id) == ("pendiente", usuario)
    assert fila.oauth_expira_en == AHORA + timedelta(minutes=10)
    assert fila.oauth_verifier_cifrado and "verifier" not in fila.oauth_verifier_cifrado
    assert fila.refresh_token_cifrado is None


async def _conexion_de(factory: Factory, profesional_id: int):
    from app.integraciones.gcal.models import GcalConexion

    async with factory() as s:
        return (await s.execute(select(GcalConexion).where(GcalConexion.profesional_id == profesional_id))).scalar_one()


@pytest.mark.parametrize("rol", ["recepcion", "admin"])
async def test_recepcion_y_admin_no_conectan_en_nombre_de_otra_y_sin_sesion_es_401(
        client: AsyncClient, session_factory: Factory, proveedor_gcal: ProveedorFalso, rol: str) -> None:
    await sembrar_mundo(session_factory)
    _, token = await crear_usuario_panel(session_factory, f"{rol}@turnos.test", [rol])
    assert (await client.post(f"{BASE}/conexion/iniciar", headers=bearer(token))).status_code == 403
    assert (await client.post(f"{BASE}/conexion/iniciar")).status_code == 401
    from app.integraciones.gcal.models import GcalConexion
    async with session_factory() as s:
        assert (await s.execute(select(GcalConexion))).first() is None


async def test_una_odontologa_sin_profesional_vinculada_recibe_403(
        client: AsyncClient, session_factory: Factory, proveedor_gcal: ProveedorFalso) -> None:
    _, token = await crear_usuario_panel(session_factory, "sin.vinculo@turnos.test", ["odontologo"])
    assert (await client.post(f"{BASE}/conexion/iniciar", headers=bearer(token))).status_code == 403


async def test_iniciar_con_una_conexion_activa_da_409_sin_cambios(
        client: AsyncClient, session_factory: Factory, proveedor_gcal: ProveedorFalso) -> None:
    mundo = await sembrar_mundo(session_factory)
    _, token = await _odontologa(session_factory, mundo)
    conexion_id = await sembrar_conexion(session_factory, mundo["ana"])
    respuesta = await client.post(f"{BASE}/conexion/iniciar", headers=bearer(token))
    assert (respuesta.status_code, respuesta.json()["motivo"]) == (409, "conexion_activa")
    assert (await conexion(session_factory, conexion_id)).estado == "activa"


async def test_sin_credenciales_responde_503_gcal_no_configurado(
        client: AsyncClient, session_factory: Factory, proveedor_gcal: ProveedorFalso,
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GCAL_CLIENT_ID")
    monkeypatch.delenv("GCAL_CLIENT_SECRET")
    mundo = await sembrar_mundo(session_factory)
    _, token = await _odontologa(session_factory, mundo)
    respuesta = await client.post(f"{BASE}/conexion/iniciar", headers=bearer(token))
    assert (respuesta.status_code, respuesta.json()["motivo"]) == (503, "gcal_no_configurado")


# --- 5.2 Callback ------------------------------------------------------------------------------------------------

def _google_exitoso() -> ProveedorHttp:
    payload = base64.urlsafe_b64encode(json.dumps({"email": "ana.prueba@example.com"}).encode()).decode().rstrip("=")
    cuerpo = {"access_token": "token-sintetico-canje", "refresh_token": "refresh-sintetico-canje", "expires_in": 3599,
              "id_token": f"h.{payload}.f"}
    return ProveedorHttp(client_id="c", client_secret="s", oauth_base_url="https://accounts.google.com",
                         token_base_url="https://oauth2.googleapis.com", api_base_url="https://www.googleapis.com",
                         zona=__import__("zoneinfo").ZoneInfo("America/Argentina/Buenos_Aires"),
                         transport=httpx.MockTransport(lambda r: httpx.Response(200, json=cuerpo)))


async def _iniciar(client: AsyncClient, factory: Factory) -> tuple[dict[str, int], str]:
    mundo = await sembrar_mundo(factory)
    _, token = await _odontologa(factory, mundo)
    url = (await client.post(f"{BASE}/conexion/iniciar", headers=bearer(token))).json()["url_autorizacion"]
    return mundo, _state(url)


async def test_autorizacion_concedida_guarda_los_tokens_cifrados_y_vuelve_al_panel(
        client: AsyncClient, session_factory: Factory, proveedor_gcal: ProveedorFalso, reloj,
        caplog: pytest.LogCaptureFixture) -> None:
    from app.main import app

    reloj(AHORA)
    mundo, state = await _iniciar(client, session_factory)
    app.dependency_overrides[get_proveedor] = _google_exitoso
    respuesta = await client.get(f"{BASE}/oauth/callback", params={"code": "codigo-sintetico", "state": state},
                                 follow_redirects=False)
    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "http://localhost:5174/#/google-calendar?resultado=conectado"
    fila = await _conexion_de(session_factory, mundo["ana"])
    assert (fila.estado, fila.cuenta_email, fila.conectada_en) == ("activa", "ana.prueba@example.com", AHORA)
    assert "refresh-sintetico-canje" not in (fila.refresh_token_cifrado or "")
    assert descifrar(fila.refresh_token_cifrado or "", CLAVE_FERNET) == "refresh-sintetico-canje"
    assert descifrar(fila.access_token_cifrado or "", CLAVE_FERNET) == "token-sintetico-canje"
    assert fila.oauth_nonce_hash is None and fila.oauth_verifier_cifrado is None and fila.sync_token is None
    async with session_factory() as s:
        auditoria = (await s.execute(select(RegistroAuditoria).where(
            RegistroAuditoria.entidad == "gcal_conexion"))).scalars().all()
    assert len(auditoria) == 1 and "token" not in json.dumps(auditoria[0].datos_despues)
    assert "token-sintetico-canje" not in caplog.text


async def test_state_adulterado_usado_o_vencido_no_canjea_el_codigo(
        client: AsyncClient, session_factory: Factory, proveedor_gcal: ProveedorFalso, reloj) -> None:
    reloj(AHORA)
    mundo, state = await _iniciar(client, session_factory)
    parametros = {"code": "codigo-sintetico"}
    adulterado = state[:-3] + ("aaa" if not state.endswith("aaa") else "bbb")
    for estado_malo in (adulterado, "no-es-un-jwt"):
        r = await client.get(f"{BASE}/oauth/callback", params={**parametros, "state": estado_malo},
                             follow_redirects=False)
        assert r.headers["location"].endswith("resultado=error_autorizacion")
    reloj(AHORA + timedelta(minutes=11))  # vencido
    r = await client.get(f"{BASE}/oauth/callback", params={**parametros, "state": state}, follow_redirects=False)
    assert r.headers["location"].endswith("resultado=error_autorizacion")
    assert "canjear_codigo" not in proveedor_gcal.llamadas
    assert (await _conexion_de(session_factory, mundo["ana"])).estado != "activa"


async def test_un_state_usado_no_sirve_dos_veces(client: AsyncClient, session_factory: Factory,
                                                 proveedor_gcal: ProveedorFalso, reloj) -> None:
    reloj(AHORA)
    mundo, state = await _iniciar(client, session_factory)
    primera = await client.get(f"{BASE}/oauth/callback", params={"code": "c1", "state": state}, follow_redirects=False)
    segunda = await client.get(f"{BASE}/oauth/callback", params={"code": "c2", "state": state}, follow_redirects=False)
    assert primera.headers["location"].endswith("resultado=conectado")
    assert segunda.headers["location"].endswith("resultado=error_autorizacion")
    assert proveedor_gcal.llamadas.count("canjear_codigo") == 1


async def test_permiso_denegado_deja_la_conexion_desconectada_sin_tokens(
        client: AsyncClient, session_factory: Factory, proveedor_gcal: ProveedorFalso, reloj) -> None:
    reloj(AHORA)
    mundo, state = await _iniciar(client, session_factory)
    r = await client.get(f"{BASE}/oauth/callback", params={"error": "access_denied", "state": state},
                         follow_redirects=False)
    assert r.headers["location"].endswith("resultado=permiso_denegado")
    fila = await _conexion_de(session_factory, mundo["ana"])
    assert (fila.estado, fila.refresh_token_cifrado, fila.access_token_cifrado) == ("desconectada", None, None)
    assert "canjear_codigo" not in proveedor_gcal.llamadas


async def test_el_canje_rechazado_por_google_vuelve_con_error_y_sin_conexion_activa(
        client: AsyncClient, session_factory: Factory, proveedor_gcal: ProveedorFalso, reloj) -> None:
    reloj(AHORA)
    mundo, state = await _iniciar(client, session_factory)
    r = await client.get(f"{BASE}/oauth/callback", params={"code": "codigo-invalido", "state": state},
                         follow_redirects=False)
    assert r.headers["location"].endswith("resultado=error_autorizacion")
    assert (await _conexion_de(session_factory, mundo["ana"])).estado == "desconectada"


# --- 5.4 Desconectar ---------------------------------------------------------------------------------------------

async def _conectada_con_eventos(factory: Factory, mundo: dict[str, int]) -> int:
    from datetime import timedelta as td

    from app.integraciones.gcal.models import EventoCalendar

    conexion_id = await sembrar_conexion(factory, mundo["ana"])
    async with factory() as s:
        for i in range(3):
            turno = await insertar_turno(factory, mundo, AHORA + td(days=2, hours=i))
            s.add(EventoCalendar(conexion_id=conexion_id, turno_id=turno, origen="sistema",
                                 google_event_id=f"evento-sistema-{i}", estado="sincronizado",
                                 inicio=AHORA + td(days=2, hours=i), fin=AHORA + td(days=2, hours=i, minutes=30)))
        s.add(EventoCalendar(conexion_id=conexion_id, origen="google", google_event_id="franja-ajena-1",
                             estado="sincronizado", inicio=AHORA + td(days=3), fin=AHORA + td(days=3, hours=1)))
        await s.commit()
    return conexion_id


async def test_la_profesional_se_desconecta_y_sus_eventos_quedan_desvinculados(
        client: AsyncClient, session_factory: Factory, proveedor_gcal: ProveedorFalso) -> None:
    mundo = await sembrar_mundo(session_factory)
    usuario, token = await _odontologa(session_factory, mundo)
    conexion_id = await _conectada_con_eventos(session_factory, mundo)
    r = await client.delete(f"{BASE}/conexiones/{mundo['ana']}", headers=bearer(token))
    assert r.status_code == 204
    fila = await conexion(session_factory, conexion_id)
    assert (fila.estado, fila.refresh_token_cifrado, fila.access_token_cifrado, fila.sync_token) == (
        "desconectada", None, None, None)
    por_origen = {(e.origen, e.estado) for e in await eventos(session_factory, conexion_id)}
    assert ("sistema", "desvinculado") in por_origen and ("sistema", "sincronizado") not in por_origen
    assert all(not e.ocupa for e in await eventos(session_factory, conexion_id) if e.origen == "google")
    assert "revocar" in proveedor_gcal.llamadas
    async with session_factory() as s:
        assert (await s.execute(select(RegistroAuditoria).where(
            RegistroAuditoria.entidad == "gcal_conexion", RegistroAuditoria.usuario_id == usuario))).first()


async def test_otra_odontologa_no_puede_desconectarla_y_admin_si(
        client: AsyncClient, session_factory: Factory, proveedor_gcal: ProveedorFalso) -> None:
    mundo = await sembrar_mundo(session_factory)
    _, token_otra = await _odontologa(session_factory, mundo, "bruno", "bruno.prueba@example.com")
    _, token_admin = await crear_usuario_panel(session_factory, "admin@turnos.test", ["admin"])
    _, token_recep = await crear_usuario_panel(session_factory, "recep@turnos.test", ["recepcion"])
    conexion_id = await sembrar_conexion(session_factory, mundo["ana"])
    assert (await client.delete(f"{BASE}/conexiones/{mundo['ana']}", headers=bearer(token_otra))).status_code == 403
    assert (await client.delete(f"{BASE}/conexiones/{mundo['ana']}", headers=bearer(token_recep))).status_code == 403
    assert (await conexion(session_factory, conexion_id)).estado == "activa"
    assert (await client.delete(f"{BASE}/conexiones/{mundo['ana']}", headers=bearer(token_admin))).status_code == 204
    assert (await client.delete(f"{BASE}/conexiones/{mundo['bruno']}", headers=bearer(token_admin))).status_code == 404


async def test_si_google_no_responde_al_revocar_igual_se_desconecta_sin_el_token_en_el_log(
        client: AsyncClient, session_factory: Factory, proveedor_gcal: ProveedorFalso,
        caplog: pytest.LogCaptureFixture) -> None:
    from app.integraciones.gcal.proveedor import ErrorTransitorio

    async def revocar(token: str) -> None:
        raise ErrorTransitorio(None)

    proveedor_gcal.revocar = revocar  # type: ignore[method-assign]
    mundo = await sembrar_mundo(session_factory)
    _, token = await _odontologa(session_factory, mundo)
    conexion_id = await sembrar_conexion(session_factory, mundo["ana"])
    assert (await client.delete(f"{BASE}/conexiones/{mundo['ana']}", headers=bearer(token))).status_code == 204
    fila = await conexion(session_factory, conexion_id)
    assert (fila.estado, fila.refresh_token_cifrado) == ("desconectada", None)
    assert "refresh-sintetico-001" not in caplog.text


async def test_al_desconectar_los_conflictos_abiertos_se_cierran(
        client: AsyncClient, session_factory: Factory, proveedor_gcal: ProveedorFalso) -> None:
    from app.integraciones.gcal.models import GcalConflicto

    mundo = await sembrar_mundo(session_factory)
    usuario, token = await _odontologa(session_factory, mundo)
    conexion_id = await _conectada_con_eventos(session_factory, mundo)
    [vinculo, *_] = [e for e in await eventos(session_factory, conexion_id) if e.origen == "sistema"]
    async with session_factory() as s:
        s.add(GcalConflicto(conexion_id=conexion_id, turno_id=vinculo.turno_id, evento_id=vinculo.id,
                            tipo="borrado_en_google", sistema_inicio=vinculo.inicio, sistema_fin=vinculo.fin))
        await s.commit()
    assert (await client.delete(f"{BASE}/conexiones/{mundo['ana']}", headers=bearer(token))).status_code == 204
    [c] = await conflictos(session_factory)
    assert (c.estado, c.resolucion, c.resuelto_por_usuario_id) == ("resuelto", "revisado", usuario)


# --- 5.5 Estado --------------------------------------------------------------------------------------------------

async def test_recepcion_ve_todas_las_profesionales_con_sus_conflictos(
        client: AsyncClient, session_factory: Factory, proveedor_gcal: ProveedorFalso, token_recepcion: str) -> None:
    from app.integraciones.gcal.models import GcalConflicto

    mundo = await sembrar_mundo(session_factory)
    conexion_id = await _conectada_con_eventos(session_factory, mundo)
    [vinculo, *_] = [e for e in await eventos(session_factory, conexion_id) if e.origen == "sistema"]
    async with session_factory() as s:
        s.add(GcalConflicto(conexion_id=conexion_id, turno_id=vinculo.turno_id, evento_id=vinculo.id,
                            tipo="movido_en_google", sistema_inicio=vinculo.inicio, sistema_fin=vinculo.fin,
                            google_inicio=vinculo.inicio, google_fin=vinculo.fin))
        await s.commit()
    r = await client.get(f"{BASE}/conexiones", headers=bearer(token_recepcion))
    assert r.status_code == 200
    por_id = {f["profesional_id"]: f for f in r.json()}
    assert por_id[mundo["ana"]]["estado"] == "activa" and por_id[mundo["ana"]]["conflictos_abiertos"] == 1
    assert por_id[mundo["ana"]]["cuenta_email"] == "ana.prueba@example.com"
    assert por_id[mundo["bruno"]]["estado"] == "sin_conectar" and por_id[mundo["bruno"]]["conflictos_abiertos"] == 0
    assert "token" not in json.dumps(r.json())


async def test_la_odontologa_ve_solo_la_suya_y_sin_sesion_es_401(
        client: AsyncClient, session_factory: Factory, proveedor_gcal: ProveedorFalso) -> None:
    mundo = await sembrar_mundo(session_factory)
    _, token = await _odontologa(session_factory, mundo)
    await sembrar_conexion(session_factory, mundo["bruno"])
    r = await client.get(f"{BASE}/conexiones", headers=bearer(token))
    assert [f["profesional_id"] for f in r.json()] == [mundo["ana"]] and r.json()[0]["estado"] == "sin_conectar"
    assert (await client.get(f"{BASE}/conexiones")).status_code == 401


async def test_una_conexion_revocada_pide_volver_a_conectar(
        client: AsyncClient, session_factory: Factory, proveedor_gcal: ProveedorFalso, token_recepcion: str) -> None:
    mundo = await sembrar_mundo(session_factory)
    await sembrar_conexion(session_factory, mundo["ana"], estado="revocada")
    fila = next(f for f in (await client.get(f"{BASE}/conexiones", headers=bearer(token_recepcion))).json()
                if f["profesional_id"] == mundo["ana"])
    assert fila["estado"] == "revocada" and fila["indicacion"] == "Volvé a conectar Google Calendar"
