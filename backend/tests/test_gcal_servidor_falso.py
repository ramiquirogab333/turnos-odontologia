"""C-10 (11.1): el servidor falso de Google y el adaptador HTTP real contra él (``httpx.ASGITransport``, sin red)."""

import base64
import hashlib
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.integraciones.gcal.contenido import armar_contenido
from app.integraciones.gcal.proveedor import (AccesoRevocado, ErrorAutorizacion, ErrorTransitorio, EtagDesactualizado,
                                              EventoDuplicado, EventoInexistente, SyncTokenVencido)
from app.integraciones.gcal.proveedor_http import ProveedorHttp
from app.integraciones.gcal.servidor_falso import EMAIL_SINTETICO, crear_app
from tests.gcal_helpers import AHORA, ciclo, configurar_entorno, eventos, sembrar_conexion
from tests.panel_helpers import insertar_turno, sembrar_mundo

BA = ZoneInfo("America/Argentina/Buenos_Aires")
INICIO = AHORA + timedelta(days=1)
ACCESO = "acceso-sintetico-abcdef"
CAL = "primary"


@pytest.fixture
def falso(monkeypatch: pytest.MonkeyPatch) -> httpx.ASGITransport:
    monkeypatch.setenv("APP_ENV", "e2e")
    return httpx.ASGITransport(app=crear_app())


def _proveedor(transporte: httpx.ASGITransport) -> ProveedorHttp:
    return ProveedorHttp(client_id="c", client_secret="s", oauth_base_url="http://gcal-falso",
                         token_base_url="http://gcal-falso", api_base_url="http://gcal-falso", zona=BA,
                         transport=transporte)


def _contenido(inicio: datetime = INICIO):
    return armar_contenido(turno_id=1, tratamiento="Limpieza", sillon="Sillón 1", inicio=inicio,
                           fin=inicio + timedelta(minutes=30), zona=BA, url_panel="http://panel")


async def _control(transporte: httpx.ASGITransport, ruta: str, **cuerpo: object) -> httpx.Response:
    async with httpx.AsyncClient(transport=transporte, base_url="http://gcal-falso") as c:
        return await c.post(f"/_control/{ruta}", json=cuerpo)


@pytest.mark.parametrize("entorno", ["test", "production", "development"])
def test_el_servidor_falso_solo_arranca_con_app_env_e2e(monkeypatch: pytest.MonkeyPatch, entorno: str) -> None:
    monkeypatch.setenv("APP_ENV", entorno)
    if entorno != "test":
        monkeypatch.setenv("MP_GATEWAY", "mercadopago")
        monkeypatch.setenv("MP_ACCESS_TOKEN", "x")
        monkeypatch.setenv("MP_WEBHOOK_SECRET", "x")
    with pytest.raises(RuntimeError, match="APP_ENV=e2e"):
        crear_app()


async def test_el_consentimiento_redirige_al_callback_con_code_y_el_state_recibido(falso) -> None:
    async with httpx.AsyncClient(transport=falso, base_url="http://gcal-falso") as c:
        r = await c.get("/o/oauth2/v2/auth", params={"redirect_uri": "http://api/cb", "state": "estado-1",
                                                     "code_challenge": "x"})
    ubicacion = urlparse(r.headers["location"])
    assert r.status_code == 302 and ubicacion.netloc == "api" and parse_qs(ubicacion.query)["state"] == ["estado-1"]
    assert parse_qs(ubicacion.query)["code"]


async def test_canje_con_pkce_renovacion_y_rechazos(falso) -> None:
    proveedor = _proveedor(falso)
    verificador = "verificador-sintetico-0123456789"
    desafio = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).decode().rstrip("=")
    async with httpx.AsyncClient(transport=falso, base_url="http://gcal-falso") as c:
        codigo = parse_qs(urlparse((await c.get("/o/oauth2/v2/auth", params={
            "redirect_uri": "http://api/cb", "state": "s", "code_challenge": desafio})).headers["location"]).query)["code"][0]
    tokens = await proveedor.canjear_codigo(codigo, verificador, "http://api/cb")
    assert tokens.refresh_token == "refresh-sintetico-e2e" and tokens.email == EMAIL_SINTETICO
    with pytest.raises(ErrorAutorizacion):  # el código es de un solo uso
        await proveedor.canjear_codigo(codigo, verificador, "http://api/cb")
    assert (await proveedor.renovar_token("refresh-sintetico-e2e")).access_token
    await _control(falso, "invalid_grant", activo=True)
    with pytest.raises(AccesoRevocado):
        await proveedor.renovar_token("refresh-sintetico-e2e")


async def test_un_pkce_que_no_coincide_se_rechaza(falso) -> None:
    proveedor = _proveedor(falso)
    async with httpx.AsyncClient(transport=falso, base_url="http://gcal-falso") as c:
        codigo = parse_qs(urlparse((await c.get("/o/oauth2/v2/auth", params={
            "redirect_uri": "http://api/cb", "state": "s", "code_challenge": "otro"})).headers["location"]).query)["code"][0]
    with pytest.raises(ErrorAutorizacion):
        await proveedor.canjear_codigo(codigo, "verificador-distinto", "http://api/cb")


async def test_contrato_de_eventos_del_adaptador_contra_el_falso(falso) -> None:
    proveedor = _proveedor(falso)
    creado = await proveedor.insertar(ACCESO, CAL, "evento-0001", _contenido())
    assert creado.etag and creado.propias["turnos_sistema"] == "1" and creado.inicio == INICIO
    with pytest.raises(EventoDuplicado):
        await proveedor.insertar(ACCESO, CAL, "evento-0001", _contenido())
    nuevo = await proveedor.actualizar(ACCESO, CAL, "evento-0001", _contenido(INICIO + timedelta(hours=3)), creado.etag or "")
    assert nuevo.inicio == INICIO + timedelta(hours=3)
    with pytest.raises(EtagDesactualizado):
        await proveedor.actualizar(ACCESO, CAL, "evento-0001", _contenido(), creado.etag or "")
    assert (await proveedor.obtener(ACCESO, CAL, "evento-0001")).id == "evento-0001"  # type: ignore[union-attr]
    assert await proveedor.obtener(ACCESO, CAL, "no-existe") is None
    await proveedor.borrar(ACCESO, CAL, "evento-0001")
    with pytest.raises(EventoInexistente):
        await proveedor.borrar(ACCESO, CAL, "evento-0001")
    with pytest.raises(EventoDuplicado):
        await proveedor.insertar(ACCESO, CAL, "evento-0001", _contenido())


async def test_listar_incremental_ocupados_y_sync_token_vencido(falso) -> None:
    proveedor = _proveedor(falso)
    ajeno = (await _control(falso, "ocupado", inicio=INICIO.isoformat(), fin=(INICIO + timedelta(hours=1)).isoformat())
             ).json()["id"]
    await _control(falso, "ocupado", inicio=(INICIO + timedelta(hours=2)).isoformat(),
                   fin=(INICIO + timedelta(hours=3)).isoformat(), ocupa=False)
    completo = await proveedor.listar(ACCESO, CAL, None, INICIO - timedelta(days=1), INICIO + timedelta(days=60))
    assert {e.id: e.ocupa for e in completo.eventos}[ajeno] is True and sorted(e.ocupa for e in completo.eventos) == [False, True]
    assert (await proveedor.listar(ACCESO, CAL, completo.sync_token, None, None)).eventos == []
    await _control(falso, "borrar", id=ajeno)
    cambio = await proveedor.listar(ACCESO, CAL, completo.sync_token, None, None)
    assert [(e.id, e.estado) for e in cambio.eventos] == [(ajeno, "cancelled")]
    await _control(falso, "invalidar_sync")
    with pytest.raises(SyncTokenVencido):
        await proveedor.listar(ACCESO, CAL, cambio.sync_token, None, None)


async def test_las_fallas_simuladas_son_transitorias_y_sin_token_es_401(falso) -> None:
    proveedor = _proveedor(falso)
    await _control(falso, "fallar", codigo=503, veces=1)
    with pytest.raises(ErrorTransitorio):
        await proveedor.insertar(ACCESO, CAL, "evento-0002", _contenido())
    assert (await proveedor.insertar(ACCESO, CAL, "evento-0002", _contenido())).id == "evento-0002"
    async with httpx.AsyncClient(transport=falso, base_url="http://gcal-falso") as c:
        assert (await c.get("/calendar/v3/calendars/primary/events")).status_code == 401


async def test_el_adaptador_real_y_el_worker_sincronizan_contra_el_falso_de_punta_a_punta(
        session_factory, falso, monkeypatch: pytest.MonkeyPatch) -> None:
    """Un turno acreditado aparece sin datos del paciente; mover el evento en "Google" abre un conflicto."""
    from tests.gcal_helpers import conflictos

    configurar_entorno(monkeypatch)
    proveedor = _proveedor(falso)
    mundo = await sembrar_mundo(session_factory)
    conexion = await sembrar_conexion(session_factory, mundo["ana"])
    await insertar_turno(session_factory, mundo, INICIO, nombre="Paciente Ficticio", telefono="+5491100000000")
    await ciclo(session_factory, proveedor)
    async with httpx.AsyncClient(transport=falso, base_url="http://gcal-falso") as c:
        [evento] = (await c.get("/_control/eventos")).json()
    assert evento["summary"] == "Turno · Limpieza dental" and "Paciente Ficticio" not in str(evento)
    assert "+5491100000000" not in str(evento)
    await _control(falso, "mover", id=evento["id"], inicio=(INICIO + timedelta(hours=2)).isoformat(),
                   fin=(INICIO + timedelta(hours=2, minutes=30)).isoformat())
    await ciclo(session_factory, proveedor)
    assert [c.tipo for c in await conflictos(session_factory, "abierto")] == ["movido_en_google"]
    assert len([e for e in await eventos(session_factory, conexion) if e.origen == "sistema"]) == 1
