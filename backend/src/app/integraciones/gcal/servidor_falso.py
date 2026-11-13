"""Servidor falso de Google (OAuth + Calendar v3) para los E2E (C-10, D11, O15). SOLO con ``APP_ENV=e2e``.

Imita el subconjunto que usa el adaptador real (``ProveedorHttp``): consentimiento al toque con una cuenta sintética,
canje con PKCE y renovación de tokens, eventos con ``etag``, ids propios, ``409`` por id repetido, ``412`` por
``If-Match`` viejo y ``syncToken`` (``410`` si se invalida). Los endpoints ``/_control/*`` simulan lo que hace la
profesional en su calendario (mover, borrar, crear un ocupado) y las fallas de Google (503, ``invalid_grant``). Nada
de esto existe en producción: ``crear_app`` se niega a arrancar con otro ``APP_ENV``. Todo es sintético (R19).

Arranque: ``uvicorn app.integraciones.gcal.servidor_falso:crear_app --factory --host 0.0.0.0 --port 8090``.
"""

import base64
import hashlib
import json
import secrets
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlencode

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from app.shared.settings import get_settings

EMAIL_SINTETICO = "profesional.prueba@example.com"
CALENDARIO = "primary"


class _Estado:
    def __init__(self) -> None:
        self.reiniciar()

    def reiniciar(self) -> None:
        self.eventos: dict[str, dict[str, Any]] = {}
        self.cambios: list[str] = []
        self.codigos: dict[str, str] = {}  # code -> code_challenge
        self.version = 0
        self.epoca = 0
        self.fallas: list[int] = []
        self.invalid_grant = False
        self.contador = 0

    def tocar(self, evento: dict[str, Any]) -> None:
        self.version += 1
        evento["etag"] = f"\"etag-{self.version}\""
        evento["updated"] = datetime.now(timezone.utc).isoformat()
        self.eventos[evento["id"]] = evento
        self.cambios.append(evento["id"])


def _instante(dato: dict[str, str]) -> datetime:
    return datetime.fromisoformat(dato["dateTime"])


def crear_app() -> FastAPI:
    """Crea la app del falso. Falla si el entorno no es ``e2e`` (nunca debe correr junto a datos reales)."""
    if get_settings().app_env != "e2e":
        raise RuntimeError("El servidor falso de Google solo arranca con APP_ENV=e2e")
    estado = _Estado()
    app = FastAPI(title="Google falso (solo e2e)")

    def autenticar(authorization: str | None) -> None:
        if not authorization or not authorization.startswith("Bearer ") or len(authorization) < 12:
            raise HTTPException(401, "Falta el token")
        if estado.fallas:
            codigo = estado.fallas.pop(0)
            raise HTTPException(codigo, "Falla simulada")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # --- OAuth -------------------------------------------------------------------------------------------------
    @app.get("/o/oauth2/v2/auth")
    async def consentimiento(redirect_uri: str, state: str, code_challenge: str = "", denegar: str = "") -> RedirectResponse:
        if denegar:
            return RedirectResponse(f"{redirect_uri}?{urlencode({'error': 'access_denied', 'state': state})}", 302)
        codigo = f"codigo-{secrets.token_hex(8)}"
        estado.codigos[codigo] = code_challenge
        return RedirectResponse(f"{redirect_uri}?{urlencode({'code': codigo, 'state': state})}", 302)

    @app.post("/token")
    async def token(request: Request) -> JSONResponse:
        datos = {k: v[0] for k, v in parse_qs((await request.body()).decode()).items()}  # form-urlencoded
        if datos.get("grant_type") == "authorization_code":
            desafio = estado.codigos.pop(str(datos.get("code")), None)
            verificador = str(datos.get("code_verifier", ""))
            esperado = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).decode().rstrip("=")
            if desafio is None or desafio != esperado:
                return JSONResponse({"error": "invalid_grant"}, status_code=400)
            carga = base64.urlsafe_b64encode(json.dumps({"email": EMAIL_SINTETICO}).encode()).decode().rstrip("=")
            return JSONResponse({"access_token": f"acceso-sintetico-{secrets.token_hex(6)}",
                                 "refresh_token": "refresh-sintetico-e2e", "expires_in": 3599,
                                 "id_token": f"cabecera.{carga}.firma"})
        if datos.get("grant_type") == "refresh_token":
            if estado.invalid_grant or datos.get("refresh_token") != "refresh-sintetico-e2e":
                return JSONResponse({"error": "invalid_grant"}, status_code=400)
            return JSONResponse({"access_token": f"acceso-sintetico-{secrets.token_hex(6)}", "expires_in": 3599})
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

    @app.post("/revoke")
    async def revocar() -> Response:
        return Response(status_code=200)

    # --- Calendar v3 -------------------------------------------------------------------------------------------
    base = "/calendar/v3/calendars/{calendario}/events"

    @app.post(base)
    async def insertar(calendario: str, request: Request, authorization: str | None = Header(None)) -> JSONResponse:
        autenticar(authorization)
        cuerpo = await request.json()
        if cuerpo.get("id") in estado.eventos:
            raise HTTPException(409, "El identificador ya existe")
        evento = {**cuerpo, "status": "confirmed"}
        estado.tocar(evento)
        return JSONResponse(evento)

    @app.get(base + "/{evento_id}")
    async def obtener(calendario: str, evento_id: str, authorization: str | None = Header(None)) -> JSONResponse:
        autenticar(authorization)
        if evento_id not in estado.eventos:
            raise HTTPException(404, "No existe")
        return JSONResponse(estado.eventos[evento_id])

    @app.patch(base + "/{evento_id}")
    async def actualizar(calendario: str, evento_id: str, request: Request, authorization: str | None = Header(None),
                         if_match: str | None = Header(None)) -> JSONResponse:
        autenticar(authorization)
        evento = estado.eventos.get(evento_id)
        if evento is None or evento["status"] == "cancelled":
            raise HTTPException(404, "No existe")
        if if_match is not None and if_match != evento["etag"]:
            raise HTTPException(412, "El evento cambió")
        evento.update(await request.json())
        estado.tocar(evento)
        return JSONResponse(evento)

    @app.delete(base + "/{evento_id}")
    async def borrar(calendario: str, evento_id: str, authorization: str | None = Header(None)) -> Response:
        autenticar(authorization)
        evento = estado.eventos.get(evento_id)
        if evento is None:
            raise HTTPException(404, "No existe")
        if evento["status"] == "cancelled":
            raise HTTPException(410, "Ya fue borrado")
        evento["status"] = "cancelled"
        estado.tocar(evento)
        return Response(status_code=204)

    @app.get(base)
    async def listar(calendario: str, request: Request, authorization: str | None = Header(None)) -> JSONResponse:
        autenticar(authorization)
        consulta = request.query_params
        token_nuevo = f"sync-{estado.epoca}-{len(estado.cambios)}"
        if "syncToken" in consulta:
            epoca, _, posicion = consulta["syncToken"].removeprefix("sync-").partition("-")
            if epoca != str(estado.epoca) or not posicion.isdigit():
                raise HTTPException(410, "syncToken vencido")
            ids = list(dict.fromkeys(estado.cambios[int(posicion):]))
            items = [estado.eventos[i] for i in ids]
        else:
            items = list(estado.eventos.values())
            if "timeMin" in consulta and "timeMax" in consulta:
                minimo = datetime.fromisoformat(consulta["timeMin"].replace("Z", "+00:00"))
                maximo = datetime.fromisoformat(consulta["timeMax"].replace("Z", "+00:00"))
                items = [e for e in items if e["status"] == "cancelled" or (
                    _instante(e["start"]) < maximo and _instante(e["end"]) > minimo)]
        return JSONResponse({"items": items, "nextSyncToken": token_nuevo})

    # --- Control del E2E (lo que hace la profesional en Google y las fallas de Google) -------------------------
    @app.get("/_control/eventos")
    async def ver_eventos() -> list[dict[str, Any]]:
        return [{"id": e["id"], "summary": e.get("summary", ""), "description": e.get("description", ""),
                 "start": e.get("start"), "end": e.get("end"), "propios": e.get("extendedProperties", {}).get("private", {})}
                for e in estado.eventos.values() if e["status"] != "cancelled"]

    @app.post("/_control/mover")
    async def mover(request: Request) -> dict[str, str]:
        datos = await request.json()
        evento = estado.eventos[datos["id"]]
        evento["start"], evento["end"] = {"dateTime": datos["inicio"]}, {"dateTime": datos["fin"]}
        estado.tocar(evento)
        return {"estado": "movido"}

    @app.post("/_control/borrar")
    async def borrar_evento(request: Request) -> dict[str, str]:
        evento = estado.eventos[(await request.json())["id"]]
        evento["status"] = "cancelled"
        estado.tocar(evento)
        return {"estado": "borrado"}

    @app.post("/_control/ocupado")
    async def ocupado(request: Request) -> dict[str, str]:
        datos = await request.json()
        estado.contador += 1
        evento = {"id": f"ajeno{estado.contador:04d}", "status": "confirmed", "summary": "Evento sintético",
                  "start": {"dateTime": datos["inicio"]}, "end": {"dateTime": datos["fin"]},
                  "transparency": "opaque" if datos.get("ocupa", True) else "transparent"}
        estado.tocar(evento)
        return {"id": evento["id"]}

    @app.post("/_control/fallar")
    async def fallar(request: Request) -> dict[str, int]:
        datos = await request.json()
        estado.fallas.extend([int(datos.get("codigo", 503))] * int(datos.get("veces", 1)))
        return {"pendientes": len(estado.fallas)}

    @app.post("/_control/invalid_grant")
    async def invalid_grant(request: Request) -> dict[str, bool]:
        estado.invalid_grant = bool((await request.json()).get("activo", True))
        return {"activo": estado.invalid_grant}

    @app.post("/_control/invalidar_sync")
    async def invalidar_sync() -> dict[str, int]:
        estado.epoca += 1
        return {"epoca": estado.epoca}

    @app.post("/_control/reiniciar")
    async def reiniciar() -> dict[str, str]:
        estado.reiniciar()
        return {"estado": "reiniciado"}

    return app
