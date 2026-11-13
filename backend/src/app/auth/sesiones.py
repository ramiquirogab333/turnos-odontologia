"""Sesión del panel en el servidor (C-15, D1-D3): crear, rotar por compare-and-swap, revocar y cargar el contexto.

Cada inicio de sesión es una fila de ``sesion_panel``. El ``sid`` viaja en los dos JWT; el servidor decide en cada
pedido si la sesión sigue abierta (no revocada, no vencida, usuario activo) y con qué roles. Todo con SQLAlchemy Core/ORM
(R14) y sin reloj propio: el ``ahora`` entra por parámetro (R4, tests sin dormir).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import create_access_token, create_refresh_token
from app.models.auth import SesionPanel
from app.models.core import Rol, Usuario, UsuarioRol

MOTIVO_LOGOUT = "logout"
MOTIVO_DESACTIVADO = "usuario_desactivado"


@dataclass(frozen=True)
class Vencimientos:
    """Vencimientos de un par de tokens: nunca después del tope absoluto de la sesión."""

    access: datetime
    refresh: datetime


@dataclass(frozen=True)
class TokensEmitidos:
    """Par de tokens firmado y el instante en que vence el refresh (para la cookie)."""

    access_token: str
    refresh_token: str
    refresh_jti: UUID
    refresh_expira_en: datetime


@dataclass(frozen=True)
class ContextoSesion:
    """Lo que el servidor sabe de una sesión en este pedido: usuario, estado y roles actuales de la base."""

    usuario_id: int
    email: str
    activo: bool
    revocada_en: datetime | None
    expira_en: datetime
    roles: list[str]


def calcular_vencimientos(ahora: datetime, expira_en: datetime, *, access_minutos: int, refresh_minutos: int) -> Vencimientos:
    """``min(ahora + duración, expira_en)`` para el access y para el refresh (D1)."""
    return Vencimientos(
        access=min(ahora + timedelta(minutes=access_minutos), expira_en),
        refresh=min(ahora + timedelta(minutes=refresh_minutos), expira_en),
    )


def emitir_tokens(
    *, sid: UUID, usuario_id: int, email: str, roles: list[str], ahora: datetime, expira_en: datetime,
    access_minutos: int, refresh_minutos: int, refresh_jti: UUID | None = None,
) -> TokensEmitidos:
    """Firma access y refresh con ``jti`` propios y el mismo ``sid``."""
    venc = calcular_vencimientos(ahora, expira_en, access_minutos=access_minutos, refresh_minutos=refresh_minutos)
    jti_refresh = refresh_jti or uuid4()
    base: dict[str, Any] = {"sub": str(usuario_id), "roles": roles, "email": email, "sid": str(sid)}
    return TokensEmitidos(
        access_token=create_access_token({**base, "jti": str(uuid4())}, ahora=ahora, expires_at=venc.access),
        refresh_token=create_refresh_token({**base, "jti": str(jti_refresh)}, ahora=ahora, expires_at=venc.refresh),
        refresh_jti=jti_refresh,
        refresh_expira_en=venc.refresh,
    )


async def crear_sesion(
    session: AsyncSession, *, usuario_id: int, ahora: datetime, maximo_horas: int, ip: str | None,
    refresh_jti: UUID | None = None,
) -> SesionPanel:
    """Abre una sesión (``flush``, sin commit): vence de forma absoluta a las ``maximo_horas``."""
    sesion = SesionPanel(
        sid=uuid4(), usuario_id=usuario_id, refresh_jti=refresh_jti or uuid4(), creada_en=ahora,
        expira_en=ahora + timedelta(hours=maximo_horas), ip_inicio=ip,
    )
    session.add(sesion)
    await session.flush()
    return sesion


def _uuid(valor: object) -> UUID | None:
    try:
        return UUID(str(valor))
    except (ValueError, AttributeError):
        return None


async def rotar_refresh(session: AsyncSession, *, sid: object, jti_presentado: object, nuevo_jti: UUID,
                        ahora: datetime) -> tuple[int, datetime] | None:
    """Compare-and-swap del refresh: solo gana quien presenta el ``jti`` vigente de una sesión abierta y sin vencer.

    Devuelve ``(usuario_id, expira_en)`` o ``None`` (cero filas). Con dos renovaciones simultáneas la segunda espera
    el lock de fila, reevalúa el ``WHERE`` con el ``jti`` ya cambiado y no actualiza nada: nunca un 500.
    """
    sid_uuid, jti_uuid = _uuid(sid), _uuid(jti_presentado)
    if sid_uuid is None or jti_uuid is None:
        return None
    fila = (await session.execute(
        update(SesionPanel)
        .where(SesionPanel.sid == sid_uuid, SesionPanel.refresh_jti == jti_uuid,
               SesionPanel.revocada_en.is_(None), SesionPanel.expira_en > ahora)
        .values(refresh_jti=nuevo_jti, renovada_en=ahora)
        .returning(SesionPanel.usuario_id, SesionPanel.expira_en)
        .execution_options(synchronize_session=False)
    )).first()
    return None if fila is None else (int(fila.usuario_id), fila.expira_en)


async def revocar_sesiones(session: AsyncSession, sids: list[object], *, motivo: str, ahora: datetime) -> int:
    """Revoca las sesiones indicadas que sigan abiertas. Idempotente: repetirlo no cambia nada."""
    validos = [u for u in (_uuid(s) for s in sids) if u is not None]
    if not validos:
        return 0
    resultado = await session.execute(
        update(SesionPanel)
        .where(SesionPanel.sid.in_(validos), SesionPanel.revocada_en.is_(None))
        .values(revocada_en=ahora, motivo_revocacion=motivo)
        .execution_options(synchronize_session=False)
    )
    return int(resultado.rowcount or 0)  # type: ignore[attr-defined]


async def revocar_de_usuario(session: AsyncSession, usuario_id: int, *, motivo: str, ahora: datetime) -> int:
    """Revoca todas las sesiones abiertas de un usuario (desactivación)."""
    resultado = await session.execute(
        update(SesionPanel)
        .where(SesionPanel.usuario_id == usuario_id, SesionPanel.revocada_en.is_(None))
        .values(revocada_en=ahora, motivo_revocacion=motivo)
        .execution_options(synchronize_session=False)
    )
    return int(resultado.rowcount or 0)  # type: ignore[attr-defined]


async def cargar_contexto(session: AsyncSession, *, sid: object, usuario_id: int) -> ContextoSesion | None:
    """Una sola consulta indexada: sesión + usuario + roles de la base (D2). ``None`` si no hay fila."""
    sid_uuid = _uuid(sid)
    if sid_uuid is None:
        return None
    fila = (await session.execute(
        select(
            Usuario.id, Usuario.email, Usuario.is_active, SesionPanel.revocada_en, SesionPanel.expira_en,
            func.array_agg(Rol.nombre).filter(Rol.nombre.is_not(None)).label("roles"),
        )
        .select_from(SesionPanel)
        .join(Usuario, Usuario.id == SesionPanel.usuario_id)
        .outerjoin(UsuarioRol, UsuarioRol.usuario_id == Usuario.id)
        .outerjoin(Rol, Rol.id == UsuarioRol.rol_id)
        .where(SesionPanel.sid == sid_uuid, Usuario.id == usuario_id)
        .group_by(Usuario.id, SesionPanel.id)
    )).first()
    if fila is None:
        return None
    return ContextoSesion(
        usuario_id=int(fila.id), email=str(fila.email), activo=bool(fila.is_active), revocada_en=fila.revocada_en,
        expira_en=fila.expira_en, roles=sorted(fila.roles or []),
    )


def sesion_vigente(contexto: ContextoSesion | None, ahora: datetime) -> bool:
    """Abierta de verdad: existe, no revocada, no vencida (exclusivo) y con usuario activo."""
    return (contexto is not None and contexto.activo and contexto.revocada_en is None
            and contexto.expira_en > ahora)


async def purgar_sesiones(session: AsyncSession, ahora: datetime, margen: timedelta, lote: int = 500) -> int:
    """Borra las sesiones cuyo vencimiento absoluto pasó hace más que ``margen`` (D8). Devuelve cuántas borró.

    Invariante: todo token de una sesión vence a más tardar en ``expira_en``, así que borrar con
    ``expira_en < ahora - margen`` nunca reabre una sesión (una revocada y no vencida se conserva). Lotes con
    ``FOR UPDATE SKIP LOCKED``: dos workers cooperan sin chocar. Un commit por lote.
    """
    total = 0
    while True:
        elegidas = (select(SesionPanel.id).where(SesionPanel.expira_en < ahora - margen)
                    .order_by(SesionPanel.id).limit(lote).with_for_update(skip_locked=True))
        resultado = await session.execute(delete(SesionPanel).where(SesionPanel.id.in_(elegidas))
                                          .execution_options(synchronize_session=False))
        borradas = int(resultado.rowcount or 0)  # type: ignore[attr-defined]
        await session.commit()
        total += borradas
        if borradas < lote:
            return total
