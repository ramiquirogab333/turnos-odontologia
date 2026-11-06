"""Puerto ``PasarelaPagos`` y verificación de la firma del webhook (D1, D6; R16, R17).

La firma se verifica SIEMPRE con este mismo código, también con la pasarela falsa: el E2E firma
igual que Mercado Pago. El manifest es ``id:{data.id};request-id:{x-request-id};ts:{ts};``.
"""

import hashlib
import hmac
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Protocol

_MS_UMBRAL = 100_000_000_000  # un ts mayor a esto está en milisegundos (Mercado Pago los envía en ms)
_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
_TS = re.compile(r"^[0-9]{1,16}$")  # solo dígitos ASCII y con tope: un ts desmedido o "²" no debe llegar a int()


class PasarelaNoDisponibleError(Exception):
    """La pasarela no respondió (timeout, red, 5xx) o rechazó la petición. Sin secretos en el mensaje."""


class PagoInexistenteError(Exception):
    """La pasarela no conoce ese ``payment_id`` (404)."""


@dataclass(frozen=True)
class PreferenciaCreada:
    """Resultado de crear la preferencia de cobro: a dónde redirigir al paciente."""

    checkout_url: str
    preferencia_id: str | None = None


@dataclass(frozen=True)
class PagoPasarela:
    """Estado de un pago consultado a la pasarela (nunca se confía en el body del webhook)."""

    id: str
    estado: str  # approved | rejected | pending | ...
    referencia_externa: str | None
    monto: Decimal | None = None
    moneda: str | None = None


class PasarelaPagos(Protocol):
    """Puerto de la pasarela de pagos; adaptadores: ``MercadoPagoPasarela`` y ``FakePasarela``."""

    async def crear_preferencia(self, *, turno_id: int, referencia_externa: str, monto: Decimal,
                                descripcion: str, vence_en: datetime) -> PreferenciaCreada:
        """Crea la preferencia de cobro y devuelve la URL de checkout."""
        ...

    async def obtener_pago(self, payment_id: str) -> PagoPasarela:
        """Consulta el pago a la pasarela."""
        ...


def _normalizar_data_id(data_id: str) -> str:
    """Mercado Pago firma el ``data.id`` alfanumérico en minúsculas."""
    return data_id.lower() if data_id.isalnum() else data_id


def calcular_firma(secreto: str, data_id: str, request_id: str, ts: str) -> str:
    """HMAC-SHA256 hexadecimal del manifest ``id;request-id;ts``."""
    manifest = f"id:{_normalizar_data_id(data_id)};request-id:{request_id};ts:{ts};"
    return hmac.new(secreto.encode(), manifest.encode(), hashlib.sha256).hexdigest()


def _partes(x_signature: str | None) -> tuple[str, str] | None:
    """Extrae ``(ts, v1)`` de ``ts=...,v1=...``; ``None`` si la cabecera es ausente o malformada."""
    if not x_signature:
        return None
    pares: dict[str, str] = {}
    for trozo in x_signature.split(","):
        clave, sep, valor = trozo.strip().partition("=")
        if sep:
            pares[clave.strip()] = valor.strip()
    ts, v1 = pares.get("ts"), pares.get("v1")
    if not ts or not v1 or not _TS.match(ts) or not _HEX64.match(v1):
        return None
    return ts, v1


def verificar_firma(*, secreto: str, x_signature: str | None, x_request_id: str | None, data_id: str,
                    ahora: datetime, tolerancia_segundos: int) -> bool:
    """True si la firma coincide (comparación en tiempo constante) y el ``ts`` está en tolerancia."""
    partes = _partes(x_signature)
    if partes is None or not x_request_id:
        return False
    ts, v1 = partes
    segundos = int(ts) / 1000 if int(ts) >= _MS_UMBRAL else int(ts)
    if abs(ahora.astimezone(timezone.utc).timestamp() - segundos) > tolerancia_segundos:
        return False
    esperada = calcular_firma(secreto, data_id, x_request_id, ts)
    return hmac.compare_digest(esperada, v1.lower())
