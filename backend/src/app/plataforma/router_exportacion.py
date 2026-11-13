"""``GET /api/panel/export`` (C-13, D9, D10; O7, O8, O11-O15): CSV por streaming, auditado antes del primer byte.

Orden de operaciones (todo antes del primer byte, para poder responder 4xx/5xx con JSON): permisos y validación; límites
(una en curso y N por hora); conexión dedicada ``REPEATABLE READ READ ONLY`` con ``statement_timeout``; ``count(*)`` en
esa misma foto; registro ``exportacion`` en una sesión aparte (si falla, no se exporta); y recién entonces el cuerpo,
que se lee con un cursor del servidor en lotes de 500 y se formatea por lote (memoria constante, sin bloquear el loop, R16).
La conexión y el lease se liberan siempre: al terminar, ante un error o si el cliente corta la descarga.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import date, datetime
from typing import Annotated, Any, Literal

import anyio
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi import Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection

from app.auth.rbac import PermissionContext, require_recepcion_o_admin
from app.panel.service import zona_clinica
from app.plataforma.auditoria import registrar
from app.plataforma.exportacion import DESCRIPTORES, EscritorCsv, Filtros, consulta, formatear_fila
from app.shared.db import get_engine, get_session_factory
from app.shared.limites import (
    RESPUESTA_429_OPENAPI,
    LimitadorSolicitudes,
    get_limitador,
    respuesta_limite_superado,
)
from app.shared.logger import get_logger
from app.shared.reloj import get_reloj
from app.shared.settings import get_settings

logger = get_logger(__name__)

router = APIRouter(prefix="/api/panel", tags=["exportacion"])

LOTE = 500
ENTIDAD_AUDITADA = {"turnos": "turno", "pacientes": "paciente", "cierres_caja": "cierre_caja"}


class ExportQuery(BaseModel):
    """Query params de ``GET /api/panel/export`` (R15): entidad y formato del conjunto soportado, rango opcional."""

    model_config = ConfigDict(extra="forbid")

    entidad: Literal["turnos", "pacientes", "cierres_caja"]
    formato: Literal["csv"]
    desde: date | None = None
    hasta: date | None = None
    incluir_inactivos: bool = False

    @model_validator(mode="after")
    def _rango_coherente(self) -> "ExportQuery":
        if self.desde is not None and self.hasta is not None and self.desde > self.hasta:
            raise ValueError("desde no puede ser posterior a hasta")
        return self


class _RespuestaConLiberacion(StreamingResponse):
    """``StreamingResponse`` que libera la conexión y el lease pase lo que pase (fin, error o cliente que corta)."""

    def __init__(self, contenido: AsyncIterator[bytes], liberar: Callable[[], Awaitable[None]], **kwargs: Any) -> None:
        super().__init__(contenido, **kwargs)
        self._liberar = liberar

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self._liberar()


async def _abrir_foto(timeout_segundos: int) -> AsyncConnection:
    """Conexión dedicada con una foto consistente (REPEATABLE READ), de solo lectura y con tope de tiempo."""
    conexion = await get_engine().connect()
    try:
        await conexion.execution_options(isolation_level="REPEATABLE READ", postgresql_readonly=True)
        await conexion.execute(select(func.set_config("statement_timeout", f"{timeout_segundos * 1000}", True)))
    except BaseException:
        await conexion.close()
        raise
    return conexion


async def _cuerpo(conexion: AsyncConnection, entidad: str, filtros: Filtros, liberar: Callable[[], Awaitable[None]]
                  ) -> AsyncIterator[bytes]:
    descriptor = DESCRIPTORES[entidad]
    zona = zona_clinica()
    escritor = EscritorCsv([c.nombre for c in descriptor.columnas])
    try:
        yield escritor.encabezado().encode("utf-8")
        resultado = await conexion.stream(consulta(entidad, filtros, zona), execution_options={"yield_per": LOTE})
        async for lote in resultado.partitions(LOTE):
            yield escritor.filas([formatear_fila(fila, descriptor.columnas, zona) for fila in lote]).encode("utf-8")
    finally:
        await liberar()


@router.get(
    "/export",
    summary="Exporta turnos, pacientes o cierres de caja en CSV (turnos y cierres: recepción y admin; pacientes: solo admin)",
    response_class=StreamingResponse,
    responses={
        200: {"description": "Archivo CSV (RFC 4180, UTF-8 con BOM, CRLF)", "content": {"text/csv": {}}},
        401: {"description": "Sin token de acceso válido"},
        403: {"description": "Sin permiso para esa entidad (pacientes: solo admin; la odontóloga no exporta)"},
        422: {"description": "Entidad, formato, rango o filtros inválidos"},
        500: {"description": "No se pudo dejar el registro de auditoría: no se exporta nada"},
        **RESPUESTA_429_OPENAPI,
    })
async def exportar(
    query: Annotated[ExportQuery, Query()],
    contexto: PermissionContext = Depends(require_recepcion_o_admin),
    limitador: LimitadorSolicitudes = Depends(get_limitador),
    ahora: datetime = Depends(get_reloj),
) -> Response:
    if query.entidad == "pacientes" and not contexto.tiene_rol("admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo el admin exporta pacientes")
    ajustes = get_settings()
    lease = f"rl:v1:export:encurso:{contexto.usuario_id}"
    en_curso = await limitador.consumir(lease, 1, ajustes.export_timeout_segundos)
    if not en_curso.permitido:
        return respuesta_limite_superado(en_curso.reintentar_en_segundos)
    liberado = False
    conexion: AsyncConnection | None = None

    async def liberar() -> None:
        """Idempotente y a salvo de cancelaciones: cierra la conexión (rollback) y libera el lease."""
        nonlocal liberado
        if liberado:
            return
        liberado = True
        with anyio.CancelScope(shield=True):
            if conexion is not None:
                await conexion.close()
            await limitador.reiniciar(lease)

    try:
        por_hora = await limitador.consumir(f"rl:v1:export:hora:{contexto.usuario_id}", ajustes.export_max_por_hora, 3600)
        if not por_hora.permitido:
            await liberar()
            return respuesta_limite_superado(por_hora.reintentar_en_segundos)
        filtros = Filtros(desde=query.desde, hasta=query.hasta, incluir_inactivos=query.incluir_inactivos)
        conexion = await _abrir_foto(ajustes.export_timeout_segundos)
        filas = (await conexion.execute(
            select(func.count()).select_from(consulta(query.entidad, filtros, zona_clinica()).subquery()))).scalar_one()
        # O8: el rastro se guarda (y confirma) con otra sesión ANTES del primer byte; si falla, no se exporta nada.
        async with get_session_factory()() as sesion:
            registrar(sesion, accion="exportacion", entidad=ENTIDAD_AUDITADA[query.entidad], entidad_id=None,
                      usuario_id=contexto.usuario_id,
                      despues={"formato": query.formato, "filas": int(filas),
                               "incluir_inactivos": query.incluir_inactivos,
                               "desde": None if query.desde is None else query.desde.isoformat(),
                               "hasta": None if query.hasta is None else query.hasta.isoformat()})
            await sesion.commit()
    except BaseException:
        await liberar()
        raise
    nombre = f"{query.entidad}_{ahora.astimezone(zona_clinica()).date().isoformat()}.csv"
    return _RespuestaConLiberacion(
        _cuerpo(conexion, query.entidad, filtros, liberar), liberar, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"', "Cache-Control": "no-store",
                 "X-Content-Type-Options": "nosniff"})
