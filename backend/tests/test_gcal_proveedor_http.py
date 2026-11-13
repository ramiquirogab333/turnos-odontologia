"""C-10 (4.3): adaptador HTTP contra Calendar v3 con ``httpx.MockTransport`` y respuestas de ejemplo de la
documentación. Sin red. Tokens sintéticos (R19)."""

import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.integraciones.gcal.contenido import armar_contenido
from app.integraciones.gcal.proveedor import (AccesoRevocado, ErrorAutorizacion, ErrorTransitorio,
                                              EtagDesactualizado, EventoDuplicado, EventoInexistente,
                                              SyncTokenVencido)
from app.integraciones.gcal.proveedor_http import ProveedorHttp

BA = ZoneInfo("America/Argentina/Buenos_Aires")
INICIO = datetime(2031, 11, 17, 13, 0, tzinfo=timezone.utc)
ACCESO = "token-sintetico-001"
Responder = Callable[[httpx.Request], httpx.Response]


def _proveedor(responder: Responder) -> tuple[ProveedorHttp, list[httpx.Request]]:
    vistas: list[httpx.Request] = []

    def manejador(request: httpx.Request) -> httpx.Response:
        vistas.append(request)
        return responder(request)

    return ProveedorHttp(client_id="cliente-sintetico", client_secret="secreto-sintetico",
                         oauth_base_url="https://accounts.google.com", token_base_url="https://oauth2.googleapis.com",
                         api_base_url="https://www.googleapis.com", zona=BA,
                         transport=httpx.MockTransport(manejador)), vistas


def _contenido():
    return armar_contenido(turno_id=7, tratamiento="Limpieza", sillon="Sillón 1", inicio=INICIO,
                           fin=INICIO + timedelta(minutes=30), zona=BA, url_panel="http://panel")


EVENTO_GOOGLE = {"kind": "calendar#event", "id": "abc12", "etag": "\"3181161784712000\"", "status": "confirmed",
                 "start": {"dateTime": "2031-11-17T10:00:00-03:00", "timeZone": "America/Argentina/Buenos_Aires"},
                 "end": {"dateTime": "2031-11-17T10:30:00-03:00"},
                 "extendedProperties": {"private": {"turnos_sistema": "1", "turno_id": "7"}}}


async def test_insertar_arma_url_cabeceras_y_cuerpo() -> None:
    proveedor, vistas = _proveedor(lambda r: httpx.Response(200, json=EVENTO_GOOGLE))
    creado = await proveedor.insertar(ACCESO, "primary", "abc12", _contenido())
    [req] = vistas
    assert req.method == "POST" and str(req.url) == "https://www.googleapis.com/calendar/v3/calendars/primary/events"
    assert req.headers["Authorization"] == f"Bearer {ACCESO}"
    cuerpo = json.loads(req.content)
    assert cuerpo["id"] == "abc12" and cuerpo["summary"] == "Turno · Limpieza" and cuerpo["transparency"] == "opaque"
    assert cuerpo["start"] == {"dateTime": "2031-11-17T10:00:00-03:00", "timeZone": "America/Argentina/Buenos_Aires"}
    assert cuerpo["extendedProperties"]["private"] == {"turnos_sistema": "1", "turno_id": "7"}
    assert creado.etag == "\"3181161784712000\"" and creado.inicio == INICIO and creado.ocupa is True


async def test_actualizar_manda_if_match_y_borrar_usa_delete() -> None:
    proveedor, vistas = _proveedor(lambda r: httpx.Response(204) if r.method == "DELETE"
                                   else httpx.Response(200, json=EVENTO_GOOGLE))
    await proveedor.actualizar(ACCESO, "primary", "abc12", _contenido(), "\"etag-1\"")
    await proveedor.borrar(ACCESO, "primary", "abc12")
    patch, delete = vistas
    assert patch.method == "PATCH" and patch.headers["If-Match"] == "\"etag-1\""
    assert patch.url.path == "/calendar/v3/calendars/primary/events/abc12"
    assert delete.method == "DELETE" and delete.url.path == "/calendar/v3/calendars/primary/events/abc12"


async def test_un_calendario_con_arroba_se_codifica_en_la_url() -> None:
    proveedor, vistas = _proveedor(lambda r: httpx.Response(204))
    await proveedor.borrar(ACCESO, "ana.prueba@example.com", "abc12")
    assert "ana.prueba%40example.com" in str(vistas[0].url)


async def test_listar_pagina_y_devuelve_el_sync_token_de_la_ultima_pagina() -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("pageToken") == "pagina-2":
            return httpx.Response(200, json={"items": [{**EVENTO_GOOGLE, "id": "dos22"}], "nextSyncToken": "sync-9"})
        return httpx.Response(200, json={"items": [EVENTO_GOOGLE], "nextPageToken": "pagina-2"})

    proveedor, vistas = _proveedor(responder)
    cambios = await proveedor.listar(ACCESO, "primary", None, INICIO, INICIO + timedelta(days=60))
    assert [e.id for e in cambios.eventos] == ["abc12", "dos22"] and cambios.sync_token == "sync-9"
    primera = vistas[0].url.params
    assert primera["singleEvents"] == "true" and primera["showDeleted"] == "true" and "timeMin" in primera
    assert "syncToken" not in primera


async def test_listar_incremental_usa_sync_token_sin_rango_y_entiende_cancelados_y_libres() -> None:
    items = [{"id": "ya-no", "status": "cancelled"},
             {"id": "libre", "status": "confirmed", "transparency": "transparent",
              "start": {"dateTime": "2031-11-17T11:00:00-03:00"}, "end": {"dateTime": "2031-11-17T12:00:00-03:00"}},
             {"id": "rechaz", "status": "confirmed", "start": {"dateTime": "2031-11-17T11:00:00-03:00"},
              "end": {"dateTime": "2031-11-17T12:00:00-03:00"},
              "attendees": [{"self": True, "responseStatus": "declined"}]},
             {"id": "diario", "status": "confirmed", "start": {"date": "2031-11-18"}, "end": {"date": "2031-11-19"}}]
    proveedor, vistas = _proveedor(lambda r: httpx.Response(200, json={"items": items, "nextSyncToken": "sync-10"}))
    cambios = await proveedor.listar(ACCESO, "primary", "sync-9", INICIO, INICIO)
    params = vistas[0].url.params
    assert params["syncToken"] == "sync-9" and "timeMin" not in params and "timeMax" not in params
    por_id = {e.id: e for e in cambios.eventos}
    assert por_id["ya-no"].estado == "cancelled" and por_id["ya-no"].ocupa is False
    assert por_id["libre"].ocupa is False and por_id["rechaz"].ocupa is False
    assert por_id["diario"].ocupa is True and por_id["diario"].inicio == datetime(2031, 11, 18, 3, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("metodo,status,esperada", [
    ("insertar", 409, EventoDuplicado), ("actualizar", 412, EtagDesactualizado), ("actualizar", 404, EventoInexistente),
    ("borrar", 410, EventoInexistente), ("borrar", 404, EventoInexistente), ("insertar", 429, ErrorTransitorio),
    ("insertar", 503, ErrorTransitorio), ("insertar", 500, ErrorTransitorio)])
async def test_los_codigos_http_se_traducen_a_errores_tipados(metodo: str, status: int, esperada: type) -> None:
    proveedor, _ = _proveedor(lambda r: httpx.Response(status, json={"error": {"message": "x"}}))
    argumentos = {"insertar": (ACCESO, "primary", "abc12", _contenido()),
                  "actualizar": (ACCESO, "primary", "abc12", _contenido(), "\"e\""),
                  "borrar": (ACCESO, "primary", "abc12")}[metodo]
    with pytest.raises(esperada):
        await getattr(proveedor, metodo)(*argumentos)


async def test_410_al_listar_es_sync_token_vencido_y_404_al_obtener_es_none() -> None:
    proveedor, _ = _proveedor(lambda r: httpx.Response(410, json={}))
    with pytest.raises(SyncTokenVencido):
        await proveedor.listar(ACCESO, "primary", "sync-viejo", None, None)
    proveedor, _ = _proveedor(lambda r: httpx.Response(404, json={}))
    assert await proveedor.obtener(ACCESO, "primary", "abc12") is None


async def test_timeout_y_error_de_red_son_transitorios() -> None:
    def falla(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("sin respuesta")

    proveedor, _ = _proveedor(falla)
    with pytest.raises(ErrorTransitorio):
        await proveedor.insertar(ACCESO, "primary", "abc12", _contenido())


async def test_renovar_token_invalid_grant_es_acceso_revocado_y_el_exito_devuelve_el_access() -> None:
    proveedor, vistas = _proveedor(lambda r: httpx.Response(400, json={"error": "invalid_grant"}))
    with pytest.raises(AccesoRevocado):
        await proveedor.renovar_token("refresh-sintetico-001")
    proveedor, vistas = _proveedor(lambda r: httpx.Response(200, json={"access_token": "token-sintetico-002",
                                                                       "expires_in": 3599}))
    tokens = await proveedor.renovar_token("refresh-sintetico-001")
    assert tokens.access_token == "token-sintetico-002" and tokens.refresh_token is None
    assert vistas[0].url.host == "oauth2.googleapis.com" and vistas[0].url.path == "/token"
    assert b"grant_type=refresh_token" in vistas[0].content


async def test_canjear_codigo_envia_pkce_y_extrae_el_email_del_id_token() -> None:
    import base64

    payload = base64.urlsafe_b64encode(json.dumps({"email": "ana.prueba@example.com"}).encode()).decode().rstrip("=")
    respuesta = {"access_token": "token-sintetico-002", "refresh_token": "refresh-sintetico-002", "expires_in": 3599,
                 "id_token": f"cabecera.{payload}.firma"}
    proveedor, vistas = _proveedor(lambda r: httpx.Response(200, json=respuesta))
    tokens = await proveedor.canjear_codigo("codigo-sintetico", "verificador-sintetico", "http://localhost/cb")
    assert (tokens.refresh_token, tokens.email) == ("refresh-sintetico-002", "ana.prueba@example.com")
    cuerpo = vistas[0].content.decode()
    assert "code_verifier=verificador-sintetico" in cuerpo and "grant_type=authorization_code" in cuerpo


async def test_canjear_codigo_rechazado_da_error_de_autorizacion_sin_el_codigo_en_el_mensaje() -> None:
    proveedor, _ = _proveedor(lambda r: httpx.Response(400, json={"error": "invalid_grant"}))
    with pytest.raises(ErrorAutorizacion) as error:
        await proveedor.canjear_codigo("codigo-sintetico", "verificador-sintetico", "http://localhost/cb")
    assert "codigo-sintetico" not in str(error.value)


async def test_ningun_mensaje_de_error_contiene_el_token() -> None:
    proveedor, _ = _proveedor(lambda r: httpx.Response(503, text=f"Bearer {ACCESO} fallo"))
    with pytest.raises(ErrorTransitorio) as error:
        await proveedor.insertar(ACCESO, "primary", "abc12", _contenido())
    assert ACCESO not in str(error.value) and ACCESO not in repr(error.value)


async def test_revocar_pega_al_endpoint_de_revocacion() -> None:
    proveedor, vistas = _proveedor(lambda r: httpx.Response(200))
    await proveedor.revocar("refresh-sintetico-001")
    assert vistas[0].url.path == "/revoke" and b"token=refresh-sintetico-001" in vistas[0].content
