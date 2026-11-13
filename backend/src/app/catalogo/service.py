"""Servicios CRUD del catálogo sobre BaseRepository + UnitOfWork (R13, R16).

Cada servicio hereda de ``BaseRepository[T]`` y opera sobre una sesión
asíncrona inyectada (el router es quien confirma la transacción, por lo que
datos de escritura y su fila de ``RegistroAuditoria`` comparten la misma
transacción atómica — RN-GL-01).

Todas las firmas están 100% tipadas y el I/O es asíncrono (no se bloquea el
event loop).
"""

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base
from app.models.core import RegistroAuditoria
from app.repositories.base import BaseRepository

ModelType = TypeVar("ModelType", bound=Base)


def _jsonable(value: Any) -> Any:
    """Convierte un valor a tipo serializable en JSONB (JSONB no admite
    datetime/date/time/Decimal nativos de asyncpg)."""
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _jsonable_dict(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if data is None:
        return None
    return {k: _jsonable(v) for k, v in data.items()}


class BaseCatalogoService(BaseRepository[ModelType]):
    """Servicio base CRUD con auditoría atómica en la misma sesión."""

    entidad: str

    def __init__(self, model: type[ModelType], session: AsyncSession, entidad: str) -> None:
        super().__init__(model, session)
        self.entidad = entidad

    def _datos(self, entity: ModelType) -> dict[str, Any]:
        return {c.name: getattr(entity, c.name) for c in entity.__table__.columns}

    async def _audit(
        self,
        accion: str,
        entidad_id: str | None,
        antes: dict[str, Any] | None,
        despues: dict[str, Any] | None,
        usuario_id: int | None,
        ip: str | None,
    ) -> None:
        self.session.add(
            RegistroAuditoria(
                usuario_id=usuario_id,
                accion=accion,
                entidad=self.entidad,
                entidad_id=entidad_id,
                datos_antes=_jsonable_dict(antes),
                datos_despues=_jsonable_dict(despues),
                ip=ip,
            )
        )

    async def create(
        self,
        data: Any,
        usuario_id: int | None = None,
        ip: str | None = None,
    ) -> ModelType:
        entity = self.model(**data.model_dump())
        await self.add(entity)
        await self.session.flush()
        # Refresh para poblar campos generados por la BD (ej. ID con Identity)
        await self.session.refresh(entity)
        await self._audit(
            "CREATE",
            str(entity.id),
            None,
            _jsonable_dict(self._datos(entity)),
            usuario_id,
            ip,
        )
        await self.session.commit()
        return entity

    async def update(
        self,
        id_: int,
        data: Any,
        usuario_id: int | None = None,
        ip: str | None = None,
    ) -> ModelType | None:
        entity = await self.get_by_id(id_)
        if entity is None:
            return None
        antes = _jsonable_dict(self._datos(entity))
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(entity, field, value)
        await self.session.flush()
        despues = _jsonable_dict(self._datos(entity))
        await self._audit(
            "UPDATE",
            str(entity.id),
            antes,
            despues,
            usuario_id,
            ip,
        )
        await self.session.commit()
        return entity

    async def delete(
        self,
        id_: int,
        usuario_id: int | None = None,
        ip: str | None = None,
    ) -> bool:
        entity = await self.get_by_id(id_)
        if entity is None:
            return False
        antes = _jsonable_dict(self._datos(entity))
        await self.session.delete(entity)
        await self.session.flush()
        await self._audit(
            "DELETE",
            str(entity.id),
            antes,
            None,
            usuario_id,
            ip,
        )
        await self.session.commit()
        return True


# ---------------------------------------------------------------------------
# Servicios concretos
# ---------------------------------------------------------------------------

from app.turnos.models import Profesional, Sillon, Tratamiento  # noqa: E402
from app.models.core import Disponibilidad  # noqa: E402


class TratamientoService(BaseCatalogoService[Tratamiento]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Tratamiento, session, "tratamiento")


class ProfesionalService(BaseCatalogoService[Profesional]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Profesional, session, "profesional")


class SillonService(BaseCatalogoService[Sillon]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Sillon, session, "sillon")


class DisponibilidadService(BaseCatalogoService[Disponibilidad]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Disponibilidad, session, "disponibilidad")
