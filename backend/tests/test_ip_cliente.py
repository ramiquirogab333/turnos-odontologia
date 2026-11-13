"""C-15 (5.1, D6/O10): IP real del cliente detrás de un proxy de confianza."""

import httpx
import pytest
from fastapi import FastAPI, Request

from app.shared.red import instalar_proxy_headers, ip_cliente


def _app(trusted: list[str]) -> FastAPI:
    app = FastAPI()
    instalar_proxy_headers(app, trusted)

    @app.get("/ip")
    async def ip(request: Request) -> dict[str, str | None]:
        return {"ip": ip_cliente(request)}

    return app


async def _ip(app: FastAPI, socket: tuple[str, int] | None, cabecera: str | None = None) -> str | None:
    transport = httpx.ASGITransport(app=app, client=socket)
    headers = {} if cabecera is None else {"X-Forwarded-For": cabecera}
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as cliente:
        return (await cliente.get("/ip", headers=headers)).json()["ip"]


async def test_proxy_de_confianza_y_cabecera_dan_la_ip_del_cliente() -> None:
    assert await _ip(_app(["192.0.2.10"]), ("192.0.2.10", 4000), "203.0.113.50") == "203.0.113.50"


async def test_proxy_dentro_de_un_cidr_de_confianza() -> None:
    assert await _ip(_app(["192.0.2.0/24"]), ("192.0.2.77", 4000), "203.0.113.51") == "203.0.113.51"


async def test_sin_proxies_de_confianza_la_cabecera_falsificada_se_ignora() -> None:
    assert await _ip(_app([]), ("198.51.100.9", 4000), "203.0.113.66") == "198.51.100.9"


async def test_un_par_que_no_es_de_confianza_no_puede_falsificar_la_cabecera() -> None:
    assert await _ip(_app(["192.0.2.10"]), ("198.51.100.9", 4000), "203.0.113.66") == "198.51.100.9"


async def test_cadena_de_proxies_toma_la_ultima_direccion_no_confiable() -> None:
    # 192.0.2.1 es otro proxy de confianza; el cliente real es el último no confiable desde la derecha.
    app = _app(["192.0.2.10", "192.0.2.1"])
    assert await _ip(app, ("192.0.2.10", 4000), "198.51.100.200, 203.0.113.50, 192.0.2.1") == "203.0.113.50"


async def test_sin_cliente_no_inventa_una_ip() -> None:
    assert await _ip(_app([]), None) is None


@pytest.mark.parametrize("texto", ["testclient", "no-es-ip", ""])
async def test_un_host_que_no_es_una_ip_valida_da_none(texto: str) -> None:
    app = FastAPI()

    @app.get("/ip")
    async def ip(request: Request) -> dict[str, str | None]:
        return {"ip": ip_cliente(request)}

    assert await _ip(app, (texto, 4000)) is None
