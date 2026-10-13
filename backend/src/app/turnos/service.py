"""Creation service: derived `fin`, pre-check + EXCLUDE safety net (D4/D5)."""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.exceptions import OverlapError, ReferenceNotFoundError
from app.turnos.models import Profesional, Sillon, Tratamiento, Turno
from app.turnos.schemas import TurnoCreate

ESTADOS_BLOQUEANTES = ("reservado", "confirmado")


def motivo_desde_mensaje(mensaje: str) -> str:
    """Infer the 409 motivo from an exclusion-violation message.

    `profesional` wins when both collide (documented default, D5).
    """
    if "turno_no_solape_profesional" in mensaje:
        return "profesional"
    if "turno_no_solape_sillon" in mensaje:
        return "sillon"
    return "profesional"


async def existe_solape(
    session: AsyncSession, columna: str, recurso_id: int, inicio: object, fin: object
) -> bool:
    """True when a blocking turno of the same resource overlaps [inicio, fin)."""
    if columna == "profesional_id":
        recurso_col = Turno.profesional_id
    elif columna == "sillon_id":
        recurso_col = Turno.sillon_id
    else:
        raise ValueError(f"columna de recurso desconocida: {columna}")
    fila = (
        await session.execute(
            select(Turno.id)
            .where(
                recurso_col == recurso_id,
                Turno.estado.in_(ESTADOS_BLOQUEANTES),
                Turno.inicio < fin,
                Turno.fin > inicio,
            )
            .limit(1)
        )
    ).first()
    return fila is not None


async def create_turno(session: AsyncSession, data: TurnoCreate) -> Turno:
    """Persist a turno deriving `fin` from the tratamiento duration.

    Raises:
        ReferenceNotFoundError: unknown profesional/sillon/tratamiento (-> 422).
        OverlapError: overlap on profesional or sillon (-> 409, never 500).
    """
    profesional = await session.get(Profesional, data.profesional_id)
    if profesional is None:
        raise ReferenceNotFoundError(campo="profesional_id")
    sillon = await session.get(Sillon, data.sillon_id)
    if sillon is None:
        raise ReferenceNotFoundError(campo="sillon_id")
    tratamiento = await session.get(Tratamiento, data.tratamiento_id)
    if tratamiento is None:
        raise ReferenceNotFoundError(campo="tratamiento_id")

    fin = data.inicio + timedelta(minutes=tratamiento.duracion_minutos)

    if await existe_solape(session, "profesional_id", data.profesional_id, data.inicio, fin):
        raise OverlapError(motivo="profesional")
    if await existe_solape(session, "sillon_id", data.sillon_id, data.inicio, fin):
        raise OverlapError(motivo="sillon")

    turno = Turno(
        profesional_id=data.profesional_id,
        sillon_id=data.sillon_id,
        tratamiento_id=data.tratamiento_id,
        inicio=data.inicio,
        fin=fin,
        estado="reservado",
    )
    session.add(turno)
    try:
        await session.flush()
    except IntegrityError as exc:
        # Race: pre-check passed but EXCLUDE fired (SQLSTATE 23P01) -> 409, never 500.
        if getattr(getattr(exc, "orig", None), "sqlstate", "") == "23P01":
            raise OverlapError(motivo=motivo_desde_mensaje(str(exc.orig))) from exc
        raise
    return turno
