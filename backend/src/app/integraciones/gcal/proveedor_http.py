"""Adaptador HTTP del puerto contra Google Calendar v3 y OAuth 2.0 (C-10, D1, R16): ``httpx`` asíncrono, timeout 10 s.

Las URLs base salen de la configuración (Google por defecto; el servidor falso solo en test/e2e). Ningún mensaje de
error, log ni excepción incluye un token: los errores se traducen por código HTTP y nunca se reenvía el cuerpo.
"""

import base64
import json
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx

from app.integraciones.gcal.contenido import ContenidoEvento
from app.integraciones.gcal.proveedor import (AccesoRevocado, CambiosGoogle, ErrorAutorizacion, ErrorProveedor,
                                              ErrorTransitorio, EtagDesactualizado, EventoDuplicado, EventoGoogle,
                                              EventoInexistente, SyncTokenVencido, TokensGoogle)
from app.shared.settings import Settings

TIMEOUT_SEGUNDOS = 10.0
MAXIMO_POR_PAGINA = 250
RAZONES_DE_CUOTA = ("rateLimitExceeded", "userRateLimitExceeded", "quotaExceeded")


class ProveedorHttp:
    """Implementación real de ``ProveedorCalendario``."""

    def __init__(self, *, client_id: str, client_secret: str, oauth_base_url: str, token_base_url: str,
                 api_base_url: str, zona: ZoneInfo, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._oauth = oauth_base_url.rstrip("/")
        self._token = token_base_url.rstrip("/")
        self._api = api_base_url.rstrip("/")
        self._zona = zona
        self._transport = transport

    @classmethod
    def desde_ajustes(cls, ajustes: Settings) -> "ProveedorHttp":
        secreto = ajustes.gcal_client_secret.get_secret_value() if ajustes.gcal_client_secret else ""
        return cls(client_id=ajustes.gcal_client_id or "", client_secret=secreto,
                   oauth_base_url=ajustes.gcal_oauth_base_url, token_base_url=ajustes.gcal_token_base_url,
                   api_base_url=ajustes.gcal_api_base_url, zona=ZoneInfo(ajustes.app_tz))

    # --- transporte ------------------------------------------------------------------------------------------
    async def _enviar(self, metodo: str, url: str, **kwargs: Any) -> httpx.Response:
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SEGUNDOS, transport=self._transport) as cliente:
                return await cliente.request(metodo, url, **kwargs)
        except httpx.HTTPError:
            raise ErrorTransitorio(None) from None

    def _evento_url(self, calendario_id: str, evento_id: str | None = None) -> str:
        base = f"{self._api}/calendar/v3/calendars/{quote(calendario_id, safe='')}/events"
        return base if evento_id is None else f"{base}/{quote(evento_id, safe='')}"

    @staticmethod
    def _cabeceras(acceso: str, **extra: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {acceso}", **extra}

    @staticmethod
    def _error_api(respuesta: httpx.Response, *, listando: bool = False) -> ErrorProveedor:
        codigo = respuesta.status_code
        if codigo == 409:
            return EventoDuplicado()
        if codigo == 410:
            return SyncTokenVencido() if listando else EventoInexistente()
        if codigo == 404:
            return EventoInexistente()
        if codigo == 412:
            return EtagDesactualizado()
        if codigo in (429, 401) or codigo >= 500:
            return ErrorTransitorio(codigo)
        if codigo == 403:
            try:
                razones = [e.get("reason") for e in respuesta.json().get("error", {}).get("errors", [])]
            except (ValueError, AttributeError):
                razones = []
            if any(r in RAZONES_DE_CUOTA for r in razones):
                return ErrorTransitorio(429)
        return ErrorProveedor(f"Google rechazó la solicitud (código {codigo})", codigo)

    # --- OAuth -----------------------------------------------------------------------------------------------
    async def canjear_codigo(self, codigo: str, verificador: str, redirect_uri: str) -> TokensGoogle:
        respuesta = await self._enviar("POST", f"{self._token}/token", data={
            "grant_type": "authorization_code", "code": codigo, "code_verifier": verificador,
            "redirect_uri": redirect_uri, "client_id": self._client_id, "client_secret": self._client_secret})
        if respuesta.status_code == 200:
            datos = respuesta.json()
            return TokensGoogle(access_token=datos["access_token"], refresh_token=datos.get("refresh_token"),
                                expira_en=datetime.now(timezone.utc) + timedelta(seconds=int(datos.get("expires_in", 3600))),
                                email=_email_del_id_token(datos.get("id_token")))
        if respuesta.status_code == 429 or respuesta.status_code >= 500:
            raise ErrorTransitorio(respuesta.status_code)
        raise ErrorAutorizacion()

    async def renovar_token(self, refresh_token: str) -> TokensGoogle:
        respuesta = await self._enviar("POST", f"{self._token}/token", data={
            "grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": self._client_id,
            "client_secret": self._client_secret})
        if respuesta.status_code == 200:
            datos = respuesta.json()
            return TokensGoogle(access_token=datos["access_token"],
                                expira_en=datetime.now(timezone.utc) + timedelta(seconds=int(datos.get("expires_in", 3600))))
        if respuesta.status_code in (400, 401):
            raise AccesoRevocado()
        raise ErrorTransitorio(respuesta.status_code)

    async def revocar(self, token: str) -> None:
        respuesta = await self._enviar("POST", f"{self._token}/revoke", data={"token": token})
        if respuesta.status_code >= 500 or respuesta.status_code == 429:
            raise ErrorTransitorio(respuesta.status_code)

    # --- eventos ---------------------------------------------------------------------------------------------
    @staticmethod
    def _cuerpo(contenido: ContenidoEvento, evento_id: str | None = None) -> dict[str, Any]:
        cuerpo: dict[str, Any] = {
            "summary": contenido.titulo, "description": contenido.descripcion,
            "start": {"dateTime": contenido.inicio.isoformat(), "timeZone": contenido.zona},
            "end": {"dateTime": contenido.fin.isoformat(), "timeZone": contenido.zona},
            "transparency": "opaque", "extendedProperties": {"private": dict(contenido.propiedades_privadas)}}
        if evento_id is not None:
            cuerpo["id"] = evento_id
        return cuerpo

    async def insertar(self, acceso: str, calendario_id: str, evento_id: str, contenido: ContenidoEvento) -> EventoGoogle:
        respuesta = await self._enviar("POST", self._evento_url(calendario_id), headers=self._cabeceras(acceso),
                                       json=self._cuerpo(contenido, evento_id))
        if respuesta.status_code not in (200, 201):
            raise self._error_api(respuesta)
        return self._parsear(respuesta.json())

    async def actualizar(self, acceso: str, calendario_id: str, evento_id: str, contenido: ContenidoEvento,
                         etag: str) -> EventoGoogle:
        respuesta = await self._enviar("PATCH", self._evento_url(calendario_id, evento_id),
                                       headers=self._cabeceras(acceso, **{"If-Match": etag}),
                                       json=self._cuerpo(contenido))
        if respuesta.status_code != 200:
            raise self._error_api(respuesta)
        return self._parsear(respuesta.json())

    async def borrar(self, acceso: str, calendario_id: str, evento_id: str) -> None:
        respuesta = await self._enviar("DELETE", self._evento_url(calendario_id, evento_id),
                                       headers=self._cabeceras(acceso))
        if respuesta.status_code not in (200, 204):
            raise self._error_api(respuesta)

    async def obtener(self, acceso: str, calendario_id: str, evento_id: str) -> EventoGoogle | None:
        respuesta = await self._enviar("GET", self._evento_url(calendario_id, evento_id),
                                       headers=self._cabeceras(acceso))
        if respuesta.status_code == 404:
            return None
        if respuesta.status_code != 200:
            raise self._error_api(respuesta)
        return self._parsear(respuesta.json())

    async def listar(self, acceso: str, calendario_id: str, sync_token: str | None, desde: datetime | None,
                     hasta: datetime | None) -> CambiosGoogle:
        parametros: dict[str, str] = {"singleEvents": "true", "showDeleted": "true",
                                      "maxResults": str(MAXIMO_POR_PAGINA)}
        if sync_token is not None:
            parametros["syncToken"] = sync_token  # con syncToken Google no admite timeMin/timeMax
        else:
            if desde is not None:
                parametros["timeMin"] = desde.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            if hasta is not None:
                parametros["timeMax"] = hasta.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        eventos: list[EventoGoogle] = []
        pagina: str | None = None
        while True:
            consulta = dict(parametros) if pagina is None else {**parametros, "pageToken": pagina}
            respuesta = await self._enviar("GET", self._evento_url(calendario_id), headers=self._cabeceras(acceso),
                                           params=consulta)
            if respuesta.status_code != 200:
                raise self._error_api(respuesta, listando=True)
            datos = respuesta.json()
            eventos.extend(self._parsear(item) for item in datos.get("items", []))
            pagina = datos.get("nextPageToken")
            if pagina is None:
                return CambiosGoogle(eventos, datos.get("nextSyncToken"))

    # --- parseo ----------------------------------------------------------------------------------------------
    def _instante(self, dato: dict[str, Any] | None) -> datetime | None:
        if not dato:
            return None
        if "dateTime" in dato:
            valor = datetime.fromisoformat(dato["dateTime"])
            return valor if valor.tzinfo else valor.replace(tzinfo=self._zona)
        if "date" in dato:  # evento de día entero: de 00:00 a 00:00 en la hora de la clínica
            return datetime.combine(date.fromisoformat(dato["date"]), time.min, tzinfo=self._zona)
        return None

    def _parsear(self, item: dict[str, Any]) -> EventoGoogle:
        estado = item.get("status", "confirmed")
        rechazado = any(a.get("self") and a.get("responseStatus") == "declined" for a in item.get("attendees", []))
        ocupa = estado != "cancelled" and item.get("transparency", "opaque") != "transparent" and not rechazado
        return EventoGoogle(id=item["id"], estado=estado, inicio=self._instante(item.get("start")),
                            fin=self._instante(item.get("end")), ocupa=ocupa, etag=item.get("etag"),
                            propias=dict(item.get("extendedProperties", {}).get("private", {})))


def _email_del_id_token(id_token: str | None) -> str | None:
    """Email del ``id_token`` recibido directo de Google por TLS en el canje (no se usa para autenticar a nadie)."""
    if not id_token or id_token.count(".") != 2:
        return None
    carga = id_token.split(".")[1]
    try:
        datos = json.loads(base64.urlsafe_b64decode(carga + "=" * (-len(carga) % 4)))
    except (ValueError, json.JSONDecodeError):
        return None
    email = datos.get("email")
    return email if isinstance(email, str) else None
