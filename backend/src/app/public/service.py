"""Servicio de reserva pública y consulta de disponibilidad (R13, R16).

Todo el I/O es asíncrono. Reglas aplicadas:
- RN-TU-03: sin solape por profesional ni por sillón (pre-check + EXCLUDE gist de C-01).
- RN-TU-04: ``fin = inicio + duracion_minutos`` derivado en el servidor.
- RN-TU-07: solo se reserva dentro de la ``Disponibilidad`` vigente (``is_active``).
- Las ``Disponibilidad.hora_*`` son horas locales de la clínica (``APP_TZ``).
- Bloquean agenda ``reservado``/``confirmado`` (R8): un ``en_espera`` (seña pendiente) NO bloquea.
- C-06: la reserva nace ``en_espera`` con vencimiento y bloque ``sena``; precio 0 nace ``reservado`` (RN-SN-06).

Concurrencia: las reservas se serializan con ``pg_advisory_xact_lock``. Sin él, dos
inserciones simultáneas del mismo slot violan a la vez EXCLUDE profesional y EXCLUDE
sillón y PostgreSQL aborta una con ``deadlock detected`` (40P01) en lugar de 23P01.
Con el lock, la perdedora espera, ve el turno ya confirmado y recibe un 409 limpio;
el EXCLUDE sigue siendo la garantía final en base de datos (R5).
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Disponibilidad, RegistroAuditoria
from app.pagos.calculo import monto_sena, vencimiento
from app.pagos.config import medios_disponibles, obtener_configuracion
from app.public.schemas import ReservaPublicaRequest
from app.shared.exceptions import ReferenceNotFoundError
from app.shared.settings import get_settings
from app.turnos.models import Profesional, Sillon, Tratamiento, Turno
from app.turnos.service import ESTADOS_BLOQUEANTES, motivo_desde_mensaje

LOCK_RESERVAS = 5_005_001  # clave arbitraria del advisory lock de reservas
LIMITE_ALTERNATIVAS = 5
DIAS_BUSQUEDA_ALTERNATIVAS = 7
SQLSTATE_EXCLUSION = "23P01"
SQLSTATE_DEADLOCK = "40P01"


class ReservaConflictoError(Exception):
    """Conflicto de solape con alternativas libres para reintento del paciente."""

    def __init__(self, motivo: str, alternativas: list[dict[str, Any]]) -> None:
        super().__init__(f"Solape por {motivo}")
        self.motivo = motivo
        self.alternativas = alternativas


class FueraDeDisponibilidadError(Exception):
    """El horario pedido no cae dentro de una franja de atención vigente (RN-TU-07)."""

    def __init__(self) -> None:
        super().__init__("El horario solicitado está fuera de la disponibilidad del profesional")


@dataclass(frozen=True)
class _Bloqueo:
    profesional_id: int
    sillon_id: int
    inicio: datetime
    fin: datetime


def _tz() -> ZoneInfo:
    return ZoneInfo(get_settings().app_tz)


def _solapa(a_ini: datetime, a_fin: datetime, b_ini: datetime, b_fin: datetime) -> bool:
    """Solape de rangos semiabiertos [ini, fin) igual que ``tstzrange(.., '[)')``."""
    return a_ini < b_fin and a_fin > b_ini


async def _cargar_bloqueos(session: AsyncSession, desde: datetime, hasta: datetime) -> list[_Bloqueo]:
    """Turnos que bloquean agenda y rozan [desde, hasta): una sola consulta por operación."""
    filas = await session.execute(
        select(Turno.profesional_id, Turno.sillon_id, Turno.inicio, Turno.fin).where(
            Turno.estado.in_(ESTADOS_BLOQUEANTES), Turno.inicio < hasta, Turno.fin > desde
        )
    )
    return [_Bloqueo(int(p), int(s), i, f) for p, s, i, f in filas.all()]


async def _sillones_activos(session: AsyncSession) -> list[Sillon]:
    return list((await session.execute(
        select(Sillon).where(Sillon.estado == "activo").order_by(Sillon.id)
    )).scalars().all())


def _sillon_libre(sillones: list[Sillon], bloqueos: list[_Bloqueo], inicio: datetime, fin: datetime,
                  preferido_id: int | None = None) -> Sillon | None:
    """Primer sillón activo sin solape en [inicio, fin); prefiere el sillón por defecto de la franja."""
    ordenados = sorted(sillones, key=lambda s: (s.id != preferido_id, s.id))
    for sillon in ordenados:
        if not any(b.sillon_id == sillon.id and _solapa(b.inicio, b.fin, inicio, fin) for b in bloqueos):
            return sillon
    return None


def _profesional_ocupado(bloqueos: list[_Bloqueo], profesional_id: int, inicio: datetime, fin: datetime) -> bool:
    return any(b.profesional_id == profesional_id and _solapa(b.inicio, b.fin, inicio, fin) for b in bloqueos)


async def _franjas_del_dia(session: AsyncSession, profesional_id: int, fecha: date,
                           ) -> list[tuple[datetime, datetime, int | None]]:
    """Franjas vigentes (inicio, fin, sillón por defecto) del profesional ese día, en hora local."""
    tz = _tz()
    filas = await session.execute(
        select(Disponibilidad).where(
            Disponibilidad.profesional_id == profesional_id,
            Disponibilidad.dia_semana == fecha.weekday(),
            Disponibilidad.is_active.is_(True),
        ).order_by(Disponibilidad.hora_inicio)
    )
    return [
        (datetime.combine(fecha, d.hora_inicio, tzinfo=tz), datetime.combine(fecha, d.hora_fin, tzinfo=tz),
         d.sillon_defecto_id)
        for d in filas.scalars().all()
    ]


async def _slots_libres(session: AsyncSession, profesional_id: int, duracion_minutos: int, desde: date,
                        hasta: date, despues_de: datetime | None = None,
                        limite: int | None = None) -> list[dict[str, Any]]:
    """Slots consecutivos de ``duracion_minutos`` donde profesional y algún sillón están libres."""
    tz = _tz()
    ahora = datetime.now(tz)
    piso = max(ahora, despues_de) if despues_de is not None else ahora
    paso = timedelta(minutes=duracion_minutos)
    bloqueos = await _cargar_bloqueos(
        session, datetime.combine(desde, datetime.min.time(), tzinfo=tz),
        datetime.combine(hasta + timedelta(days=1), datetime.min.time(), tzinfo=tz),
    )
    sillones = await _sillones_activos(session)
    slots: list[dict[str, Any]] = []
    fecha = desde
    while fecha <= hasta:
        for franja_ini, franja_fin, sillon_defecto in await _franjas_del_dia(session, profesional_id, fecha):
            actual = franja_ini
            while actual + paso <= franja_fin:
                fin_slot = actual + paso
                if actual > piso and not _profesional_ocupado(bloqueos, profesional_id, actual, fin_slot):
                    sillon = _sillon_libre(sillones, bloqueos, actual, fin_slot, sillon_defecto)
                    if sillon is not None:
                        slots.append({"inicio": actual, "fin": fin_slot,
                                      "profesional_id": profesional_id, "sillon_id": int(sillon.id)})
                        if limite is not None and len(slots) >= limite:
                            return slots
                actual = fin_slot
        fecha += timedelta(days=1)
    return slots


async def consultar_disponibilidad(session: AsyncSession, profesional_id: int, tratamiento_id: int,
                                   desde: date, hasta: date) -> list[dict[str, Any]]:
    """Calcula slots libres entre ``desde`` y ``hasta`` (inclusive, fechas locales de la clínica)."""
    tratamiento = await session.get(Tratamiento, tratamiento_id)
    if tratamiento is None:
        raise ReferenceNotFoundError(campo="tratamiento_id")
    if await session.get(Profesional, profesional_id) is None:
        raise ReferenceNotFoundError(campo="profesional_id")
    return await _slots_libres(session, profesional_id, tratamiento.duracion_minutos, desde, hasta)


async def _alternativas(session: AsyncSession, profesional_id: int, inicio: datetime,
                        duracion_minutos: int) -> list[dict[str, Any]]:
    """Próximos slots libres a partir de ``inicio`` (mismo profesional), para reorientar al paciente."""
    desde = inicio.astimezone(_tz()).date()
    slots = await _slots_libres(
        session, profesional_id, duracion_minutos, desde,
        desde + timedelta(days=DIAS_BUSQUEDA_ALTERNATIVAS), despues_de=inicio, limite=LIMITE_ALTERNATIVAS,
    )
    return [{"inicio": s["inicio"].isoformat(), "fin": s["fin"].isoformat(), "sillon_id": s["sillon_id"]}
            for s in slots]


async def _franja_que_contiene(session: AsyncSession, profesional_id: int, inicio: datetime,
                               fin: datetime) -> int | None | bool:
    """Devuelve el sillón por defecto de la franja que contiene [inicio, fin); False si no hay (RN-TU-07)."""
    for f_ini, f_fin, sillon_defecto in await _franjas_del_dia(
        session, profesional_id, inicio.astimezone(_tz()).date()
    ):
        if f_ini <= inicio and fin <= f_fin:
            return sillon_defecto
    return False


async def reservar_turno_publico(session: AsyncSession, data: ReservaPublicaRequest) -> dict[str, Any]:
    """Crea un turno público con sillón auto-asignado y código de gestión; confirma la transacción.

    Raises:
        ReferenceNotFoundError: profesional/tratamiento inexistente (422).
        FueraDeDisponibilidadError: fuera de la franja vigente (422).
        ReservaConflictoError: solape de profesional o sillón, con alternativas (409).
    """
    profesional = await session.get(Profesional, data.profesional_id)
    if profesional is None:
        raise ReferenceNotFoundError(campo="profesional_id")
    tratamiento = await session.get(Tratamiento, data.tratamiento_id)
    if tratamiento is None:
        raise ReferenceNotFoundError(campo="tratamiento_id")

    inicio = data.inicio
    fin = inicio + timedelta(minutes=tratamiento.duracion_minutos)  # RN-TU-04

    sillon_defecto = await _franja_que_contiene(session, data.profesional_id, inicio, fin)
    if sillon_defecto is False:
        raise FueraDeDisponibilidadError()

    # Serializa reservas concurrentes (ver docstring del módulo); se libera al commit/rollback.
    await session.execute(select(func.pg_advisory_xact_lock(LOCK_RESERVAS)))

    bloqueos = await _cargar_bloqueos(session, inicio, fin)
    if _profesional_ocupado(bloqueos, data.profesional_id, inicio, fin):
        raise await _conflicto(session, "profesional", data, tratamiento.duracion_minutos)
    sillon = _sillon_libre(await _sillones_activos(session), bloqueos, inicio, fin,
                           sillon_defecto if isinstance(sillon_defecto, int) else None)
    if sillon is None:
        raise await _conflicto(session, "sillon", data, tratamiento.duracion_minutos)

    config = await obtener_configuracion(session)
    monto = monto_sena(tratamiento.precio_base, config.sena_porcentaje)  # RN-SN-03
    exento = monto <= 0  # RN-SN-06: precio 0 -> sin seña, nace reservado
    vence_en = None if exento else vencimiento(
        datetime.now(timezone.utc), config.expiracion_mp_minutos, inicio)  # RN-SN-07

    turno = Turno(
        profesional_id=data.profesional_id, sillon_id=sillon.id, tratamiento_id=data.tratamiento_id,
        paciente_id=None, inicio=inicio, fin=fin, estado="reservado" if exento else "en_espera",
        en_espera_vence_en=vence_en,
        codigo_gestion=str(uuid.uuid4()), contacto_nombre=data.nombre, contacto_telefono=data.telefono,
    )
    session.add(turno)
    try:
        await session.flush()
        await session.refresh(turno)  # Identity: id no se rellena tras flush sin refresh
        session.add(RegistroAuditoria(  # RN-GL-01: misma transacción atómica (sin PII de contacto)
            usuario_id=None, accion="CREATE", entidad="turno", entidad_id=str(turno.id),
            datos_despues={
                "profesional_id": turno.profesional_id, "sillon_id": turno.sillon_id,
                "tratamiento_id": turno.tratamiento_id, "inicio": turno.inicio.isoformat(),
                "fin": turno.fin.isoformat(), "estado": turno.estado, "origen": "reserva_publica",
            },
            ip=None,
        ))
        await session.commit()
    except (IntegrityError, DBAPIError) as exc:
        await session.rollback()
        sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", "")
        if sqlstate in (SQLSTATE_EXCLUSION, SQLSTATE_DEADLOCK):  # red de seguridad: nunca 500
            motivo = motivo_desde_mensaje(str(exc.orig)) if sqlstate == SQLSTATE_EXCLUSION else "profesional"
            raise await _conflicto(session, motivo, data, tratamiento.duracion_minutos) from exc
        raise

    sena = None if exento or vence_en is None else {
        "monto": monto, "vence_en": vence_en, "medios_habilitados": medios_disponibles(config),
        "texto_politica_reembolso": config.texto_politica_reembolso}
    return {"turno_id": int(turno.id), "codigo_gestion": turno.codigo_gestion or "",
            "estado": turno.estado, "inicio": turno.inicio, "fin": turno.fin, "sena": sena}


async def _conflicto(session: AsyncSession, motivo: str, data: ReservaPublicaRequest,
                     duracion_minutos: int) -> ReservaConflictoError:
    """Arma el 409 con alternativas; libera el lock y cualquier estado de la transacción."""
    alternativas = await _alternativas(session, data.profesional_id, data.inicio, duracion_minutos)
    await session.rollback()
    return ReservaConflictoError(motivo=motivo, alternativas=alternativas)
