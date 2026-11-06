"""Webhook de Mercado Pago (C-06, D6; R15, R16, R17). Sin JWT: la autenticidad la da la firma HMAC.

Nunca se confía en el body: el pago se consulta a la pasarela con el ``data.id`` firmado. Responde 200 a
todo lo que no sea reintentable (para que Mercado Pago no insista) y 503 si la pasarela no responde.
"""

from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.pagos.deps import get_pasarela
from app.pagos.errores import OperacionReintentableError
from app.pagos.models import PagoSena
from app.pagos.pasarela import (
    PagoInexistenteError,
    PasarelaNoDisponibleError,
    PasarelaPagos,
    verificar_firma,
)
from app.pagos.service import acreditar_pago
from app.shared.db import get_session
from app.shared.logger import get_logger
from app.shared.settings import get_settings

logger = get_logger(__name__)
router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


async def _leer_body(request: Request) -> dict[str, Any]:
    try:
        cuerpo = await request.json()
    except ValueError:
        return {}
    return cuerpo if isinstance(cuerpo, dict) else {}


@router.post(
    "/mercadopago",
    summary="Notificación de pago de Mercado Pago (firma HMAC verificada)",
    responses={
        200: {"description": "Procesada o ignorada (idempotente)"},
        401: {"description": "Firma ausente, inválida o con timestamp fuera de tolerancia"},
        503: {"description": "La pasarela no respondió: Mercado Pago reintenta"},
    },
)
async def webhook_mercadopago(
    request: Request,
    x_signature: Annotated[str | None, Header()] = None,
    x_request_id: Annotated[str | None, Header()] = None,
    data_id_query: Annotated[str | None, Query(alias="data.id")] = None,
    tipo_query: Annotated[str | None, Query(alias="type")] = None,
    session: AsyncSession = Depends(get_session),
    pasarela: PasarelaPagos = Depends(get_pasarela),
) -> JSONResponse:
    """Verifica la firma, consulta el pago y, si está aprobado, acredita la seña."""
    settings = get_settings()
    if settings.mp_webhook_secret is None:  # falla cerrado: sin secreto no se acepta nada
        logger.error("webhook mercadopago: MP_WEBHOOK_SECRET no configurado")
        return JSONResponse(status_code=503, content={"detail": "Webhook no configurado"})

    cuerpo = await _leer_body(request)
    datos = cuerpo.get("data") if isinstance(cuerpo.get("data"), dict) else {}
    data_id = data_id_query or (str(datos["id"]) if "id" in datos else None)
    if not data_id or not verificar_firma(
        secreto=settings.mp_webhook_secret.get_secret_value(), x_signature=x_signature,
        x_request_id=x_request_id, data_id=data_id, ahora=datetime.now(timezone.utc),
        tolerancia_segundos=settings.mp_webhook_tolerancia_segundos,
    ):
        return JSONResponse(status_code=401, content={"detail": "Firma inválida"})

    tipo = tipo_query or cuerpo.get("type")
    if tipo != "payment":
        return JSONResponse(content={"status": "ignorado"})

    try:
        pago_pasarela = await pasarela.obtener_pago(data_id)
    except PagoInexistenteError:
        logger.info("webhook mercadopago: pago desconocido para la pasarela (data.id=%s)", data_id)
        return JSONResponse(content={"status": "ignorado"})
    except PasarelaNoDisponibleError:
        return JSONResponse(status_code=503, content={"detail": "Pasarela no disponible"})

    if pago_pasarela.estado != "approved":
        logger.info("webhook mercadopago: pago %s en estado %s (referencia %s)", pago_pasarela.id,
                    pago_pasarela.estado, pago_pasarela.referencia_externa)
        return JSONResponse(content={"status": "ignorado"})

    pago_id = None
    if pago_pasarela.referencia_externa:
        pago_id = (await session.execute(
            select(PagoSena.id).where(PagoSena.referencia_externa == pago_pasarela.referencia_externa)
        )).scalar_one_or_none()
    if pago_id is None:
        logger.info("webhook mercadopago: referencia desconocida %s (estado %s)",
                    pago_pasarela.referencia_externa, pago_pasarela.estado)
        return JSONResponse(content={"status": "ignorado"})

    try:
        resultado = await acreditar_pago(session, pago_id, mp_payment_id=pago_pasarela.id,
                                         monto_reportado=pago_pasarela.monto, moneda_reportada=pago_pasarela.moneda)
    except OperacionReintentableError:  # Mercado Pago reintenta; jamás se convierte en un reembolso
        return JSONResponse(status_code=503, content={"detail": "Reintentá más tarde"})
    logger.info("webhook mercadopago: referencia %s -> %s", pago_pasarela.referencia_externa, resultado.efecto)
    return JSONResponse(content={"status": resultado.efecto})
