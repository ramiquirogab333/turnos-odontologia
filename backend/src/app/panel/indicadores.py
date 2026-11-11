"""Indicadores del panel (C-12, D7): ocupación por sillón y día, ausentismo y recupero.

Una o dos consultas agrupadas por pantalla, sin tablas de agregados. ``ESTADOS_BLOQUEANTES`` es la única fuente de
"ocupa agenda": ``en_espera`` queda fuera por construcción (R8). El día de un turno es el de la clínica en que empieza.
"""

from collections import defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.caja.calculo import limites_del_dia
from app.caja.schemas import RangoFechas
from app.models.core import Disponibilidad
from app.pagos.models import PagoSena
from app.panel.calculo_indicadores import minutos_de_atencion, porcentaje, tasa
from app.panel.schemas_indicadores import (
    AusentismoOut,
    AusentismoProfesionalOut,
    OcupacionDiaOut,
    OcupacionOut,
    OcupacionQuery,
    OcupacionSillonOut,
    RecuperoOut,
)
from app.panel.service import zona_clinica
from app.shared.exceptions import ReferenceNotFoundError
from app.turnos.models import Profesional, Sillon, Turno
from app.turnos.service import ESTADOS_BLOQUEANTES

ESTADOS_OCUPACION = ESTADOS_BLOQUEANTES + ("ausente",)


def _dias(desde: date, hasta: date) -> list[date]:
    return [desde + timedelta(days=i) for i in range((hasta - desde).days + 1)]


async def consultar_ocupacion(session: AsyncSession, query: OcupacionQuery) -> OcupacionOut:
    """Por sillón y día: minutos ocupados, de atención, porcentaje, turnos y minutos perdidos por ausentes (O11).

    Los minutos de atención son la unión de las franjas ACTIVAS de ese día de la semana, solo para sillones activos; se
    usa la disponibilidad actual (no hay historial). Raises: ``ReferenceNotFoundError`` si ``sillon_id`` no existe.
    """
    if query.sillon_id is not None and await session.get(Sillon, query.sillon_id) is None:
        raise ReferenceNotFoundError(campo="sillon_id")
    zona = zona_clinica()
    desde_utc, _ = limites_del_dia(query.desde, zona)
    _, hasta_utc = limites_del_dia(query.hasta, zona)
    dia_local = func.date(func.timezone(zona.key, Turno.inicio))
    minutos = func.sum(func.extract("epoch", Turno.fin - Turno.inicio) / 60)
    filtro = [Turno.inicio >= desde_utc, Turno.inicio < hasta_utc, Turno.estado.in_(ESTADOS_OCUPACION)]
    if query.sillon_id is not None:
        filtro.append(Turno.sillon_id == query.sillon_id)
    filas = (await session.execute(
        select(Turno.sillon_id, dia_local, Turno.estado, minutos, func.count())
        .where(*filtro).group_by(Turno.sillon_id, dia_local, Turno.estado))).all()
    ocupados: dict[tuple[int, date], int] = defaultdict(int)
    perdidos: dict[tuple[int, date], int] = defaultdict(int)
    cantidad: dict[tuple[int, date], int] = defaultdict(int)
    con_turnos: set[int] = set()
    for sillon_id, dia, estado, mins, n in filas:
        clave = (sillon_id, dia)
        con_turnos.add(sillon_id)
        if estado == "ausente":
            perdidos[clave] += int(mins)
        else:
            ocupados[clave] += int(mins)
            cantidad[clave] += int(n)

    franjas_por_dia: dict[int, list[tuple[time, time]]] = defaultdict(list)
    for dia_semana, inicio, fin in (await session.execute(
            select(Disponibilidad.dia_semana, Disponibilidad.hora_inicio, Disponibilidad.hora_fin)
            .where(Disponibilidad.is_active.is_(True)))).all():
        franjas_por_dia[dia_semana].append((inicio, fin))
    atencion_por_semana = {d: minutos_de_atencion(f) for d, f in franjas_por_dia.items()}

    consulta = select(Sillon).order_by(Sillon.id)
    if query.sillon_id is not None:
        consulta = consulta.where(Sillon.id == query.sillon_id)
    sillones = [s for s in (await session.execute(consulta)).scalars() if s.estado == "activo" or s.id in con_turnos]
    dias = _dias(query.desde, query.hasta)
    salida: list[OcupacionSillonOut] = []
    for s in sillones:
        filas_dia: list[OcupacionDiaOut] = []
        for d in dias:
            atencion = atencion_por_semana.get(d.weekday(), 0) if s.estado == "activo" else 0
            ocup = ocupados[(s.id, d)]
            filas_dia.append(OcupacionDiaOut(
                dia=d, minutos_ocupados=ocup, minutos_atencion=atencion, porcentaje=porcentaje(ocup, atencion),
                turnos=cantidad[(s.id, d)], minutos_perdidos=perdidos[(s.id, d)]))
        salida.append(OcupacionSillonOut(sillon_id=s.id, nombre=s.nombre, estado=s.estado,  # type: ignore[arg-type]
                                         dias=filas_dia))
    return OcupacionOut(desde=query.desde, hasta=query.hasta, sillones=salida)


async def consultar_ausentismo(session: AsyncSession, rango: RangoFechas, ahora: datetime) -> AusentismoOut:
    """Atendidos, ausentes y tasa (total y por profesional), ``sin_marcar`` y recupero por señas retenidas (O12)."""
    zona = zona_clinica()
    desde_utc, _ = limites_del_dia(rango.desde, zona)
    _, hasta_utc = limites_del_dia(rango.hasta, zona)
    en_rango = and_(Turno.inicio >= desde_utc, Turno.inicio < hasta_utc)
    filas = (await session.execute(
        select(Turno.profesional_id, Profesional.nombre,
               func.count().filter(Turno.estado == "atendido"),
               func.count().filter(Turno.estado == "ausente"),
               func.count().filter(and_(Turno.estado.in_(("reservado", "confirmado")), Turno.fin < ahora)))
        .join(Profesional, Profesional.id == Turno.profesional_id).where(en_rango)
        .group_by(Turno.profesional_id, Profesional.nombre).order_by(Profesional.nombre, Turno.profesional_id))).all()
    por_profesional = [
        AusentismoProfesionalOut(profesional_id=pid, nombre=nombre, atendidos=a, ausentes=b, tasa=tasa(b, a),
                                 sin_marcar=c)
        for pid, nombre, a, b, c in filas if a or b or c]
    atendidos, ausentes = sum(p.atendidos for p in por_profesional), sum(p.ausentes for p in por_profesional)
    retenidas, importe = (await session.execute(
        select(func.count(), func.coalesce(func.sum(func.coalesce(PagoSena.monto_reportado, PagoSena.monto)), 0))
        .select_from(Turno).join(PagoSena, PagoSena.turno_id == Turno.id)
        .where(en_rango, Turno.estado == "ausente", PagoSena.estado == "no_reembolsado"))).one()
    return AusentismoOut(
        desde=rango.desde, hasta=rango.hasta, atendidos=atendidos, ausentes=ausentes, tasa=tasa(ausentes, atendidos),
        sin_marcar=sum(p.sin_marcar for p in por_profesional), por_profesional=por_profesional,
        recupero=RecuperoOut(senas_retenidas=retenidas, importe_retenido=importe,
                             porcentaje=porcentaje(retenidas, ausentes) if ausentes else None))
