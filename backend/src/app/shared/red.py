"""IP real del cliente (C-15, D6): el middleware de proxies y la lectura validada (R13)."""

import ipaddress

from fastapi import FastAPI, Request
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware


def instalar_proxy_headers(app: FastAPI, trusted_proxies: list[str]) -> None:
    """Monta ``ProxyHeadersMiddleware`` con la lista de proxies de confianza (IPs o CIDR).

    Con la lista vacía no se confía en ninguna cabecera ``X-Forwarded-For``: rige la IP del socket.
    Con proxies de confianza se toma la última dirección no confiable (de derecha a izquierda).
    """
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=trusted_proxies)  # type: ignore[arg-type]


def ip_cliente(request: Request) -> str | None:
    """IP del cliente validada con ``ipaddress``; ``None`` si no hay cliente o no es una IP (nunca un texto inventado)."""
    if request.client is None:
        return None
    try:
        return str(ipaddress.ip_address(request.client.host))
    except ValueError:
        return None
