"""Puerto del proveedor de WhatsApp y sus implementaciones (C-09, D4).

v1 es MANUAL (RN-WA-03, sin API paga): ``ProveedorManual`` no envía nada y deja el recordatorio esperando a recepción.
El dominio no depende de ``wa.me``: migrar a una API de pago es escribir otra implementación de este puerto.
``ProveedorFalso`` existe solo para ejercitar los reintentos en los tests (``WHATSAPP_PROVEEDOR=falso`` exige APP_ENV=test).
"""

from dataclasses import dataclass
from typing import Literal, Protocol

from app.shared.settings import get_settings

ResultadoProveedor = Literal["enviado", "requiere_accion_manual"]


class ErrorTransitorioProveedor(Exception):
    """El proveedor falló de forma recuperable: se reintenta con espera creciente (O10)."""


@dataclass(frozen=True)
class DatosEnvio:
    """Lo que un proveedor automático necesita; el mensaje se arma al vuelo y nunca se guarda ni se loguea (R19)."""

    recordatorio_id: int
    telefono: str
    texto: str


class ProveedorWhatsApp(Protocol):
    """Quien entrega (o deja listo para entregar) un recordatorio."""

    async def procesar(self, datos: DatosEnvio) -> ResultadoProveedor: ...


class ProveedorManual:
    """v1: no envía; recepción abre el link ``wa.me`` desde el panel."""

    async def procesar(self, datos: DatosEnvio) -> ResultadoProveedor:
        return "requiere_accion_manual"


class ProveedorFalso:
    """Solo tests: responde según una secuencia (``ErrorTransitorioProveedor``, o un resultado) y la repite al final."""

    def __init__(self, respuestas: list[ResultadoProveedor | Exception]) -> None:
        self._respuestas = respuestas
        self.llamadas = 0

    async def procesar(self, datos: DatosEnvio) -> ResultadoProveedor:
        respuesta = self._respuestas[min(self.llamadas, len(self._respuestas) - 1)]
        self.llamadas += 1
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta


def obtener_proveedor() -> ProveedorWhatsApp:
    """Proveedor según ``WHATSAPP_PROVEEDOR``: ``manual`` siempre; ``falso`` es solo de pruebas."""
    if get_settings().whatsapp_proveedor == "falso":
        return ProveedorFalso(["requiere_accion_manual"])
    return ProveedorManual()
