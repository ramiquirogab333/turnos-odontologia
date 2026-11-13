"""``GET /api/panel/auditoria`` y ``GET /api/panel/usuarios`` (C-13, D7; O3, O6): solo admin, keyset, un SELECT con JOIN."""

from datetime import datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import PermissionContext, require_admin
from app.models.core import RegistroAuditoria, Usuario
from app.plataforma.auditoria import registrar
from app.plataforma.cursor import CursorInvalidoError, codificar_cursor, decodificar_cursor
from app.plataforma.schemas import AuditoriaPagina, AuditoriaQuery, RegistroAuditoriaOut, UsuarioDirectorioOut, UsuarioRef
from app.plataforma.tipos_auditoria import clasificar, condicion_de_tipo
from app.panel.service import zona_clinica
from app.shared.db import get_session
from app.shared.reloj import get_reloj

router = APIRouter(prefix="/api/panel", tags=["auditoria"])

_ERRORES = {
    401: {"description": "Sin token de acceso válido"},
    403: {"description": "Solo admin"},
}


def _origen(datos: object) -> str | None:
    if isinstance(datos, dict):
        origen = datos.get("origen")
        return origen if isinstance(origen, str) else None
    return None


@router.get(
    "/auditoria", response_model=AuditoriaPagina,
    summary="Consulta de la auditoría (solo admin): del más reciente al más antiguo, filtros y cursor",
    responses={**_ERRORES, 422: {"description": "Rango, tipo, cursor o paginación inválidos"}})
async def consultar_auditoria(
    query: Annotated[AuditoriaQuery, Query()],
    contexto: PermissionContext = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    ahora: datetime = Depends(get_reloj),
) -> AuditoriaPagina:
    zona = zona_clinica()
    try:
        desde, hasta = query.rango(ahora.astimezone(zona).date())
        ancla = decodificar_cursor(query.cursor) if query.cursor else None
    except (ValueError, CursorInvalidoError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    inicio = datetime.combine(desde, time.min, tzinfo=zona)
    fin = datetime.combine(hasta + timedelta(days=1), time.min, tzinfo=zona)  # el día de ``hasta`` entero

    consulta = (select(RegistroAuditoria, Usuario.id, Usuario.nombre_completo)
                .outerjoin(Usuario, Usuario.id == RegistroAuditoria.usuario_id)
                .where(RegistroAuditoria.created_at >= inicio, RegistroAuditoria.created_at < fin))
    if query.entidad is not None:
        consulta = consulta.where(RegistroAuditoria.entidad == query.entidad)
    if query.entidad_id is not None:
        consulta = consulta.where(RegistroAuditoria.entidad_id == query.entidad_id)
    if query.usuario_id is not None:
        consulta = consulta.where(RegistroAuditoria.usuario_id == query.usuario_id)
    if query.tipo is not None:
        consulta = consulta.where(condicion_de_tipo(query.tipo))
    if ancla is not None:
        consulta = consulta.where(tuple_(RegistroAuditoria.created_at, RegistroAuditoria.id) < tuple_(*ancla))
    filas = (await session.execute(consulta.order_by(RegistroAuditoria.created_at.desc(), RegistroAuditoria.id.desc())
                                   .limit(query.por_pagina + 1))).all()

    hay_mas = len(filas) > query.por_pagina
    pagina = filas[:query.por_pagina]
    items = []
    for registro, usuario_id, nombre in pagina:
        tipo = clasificar(registro.accion, registro.entidad, _origen(registro.datos_despues))
        items.append(RegistroAuditoriaOut(
            id=registro.id, fecha_hora=registro.created_at.astimezone(zona),
            usuario=None if usuario_id is None else UsuarioRef(id=usuario_id, nombre_completo=nombre),
            accion=registro.accion, tipo=tipo.codigo, tipo_etiqueta=tipo.etiqueta, entidad=registro.entidad,
            entidad_id=registro.entidad_id, datos_antes=registro.datos_antes, datos_despues=registro.datos_despues,
            ip=registro.ip))
    siguiente = None
    if hay_mas:
        ultimo = pagina[-1][0]
        siguiente = codificar_cursor(ultimo.created_at, ultimo.id)
    # Sin rastro no se entrega nada: la lectura se registra y confirma antes de responder (D7).
    registrar(session, accion="lectura_auditoria", entidad="auditoria", entidad_id=None, usuario_id=contexto.usuario_id,
              despues=query.filtros_auditables(desde, hasta))
    await session.commit()
    return AuditoriaPagina(items=items, siguiente=siguiente)


@router.get(
    "/usuarios", response_model=list[UsuarioDirectorioOut],
    summary="Directorio mínimo de usuarios del panel (solo admin): id, nombre y si está activo; sin email ni roles",
    responses=_ERRORES)
async def directorio_usuarios(
    contexto: PermissionContext = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[UsuarioDirectorioOut]:
    filas = (await session.execute(
        select(Usuario.id, Usuario.nombre_completo, Usuario.is_active).order_by(Usuario.nombre_completo, Usuario.id))).all()
    return [UsuarioDirectorioOut(id=i, nombre_completo=n, activo=a) for i, n, a in filas]
