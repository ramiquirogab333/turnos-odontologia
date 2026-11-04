"""Generic async BaseRepository for domain entities (R13, R16)."""

from typing import Generic, Sequence, TypeVar
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Repositorio base asíncrono con operaciones CRUD estándar."""

    def __init__(self, model: type[ModelType], session: AsyncSession) -> None:
        self.model = model
        self.session = session

    async def get_by_id(self, id_: int) -> ModelType | None:
        """Obtiene una entidad por su ID primario."""
        return await self.session.get(self.model, id_)

    async def list_all(self, limit: int = 100, offset: int = 0) -> Sequence[ModelType]:
        """Lista entidades con paginación."""
        stmt = select(self.model).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def add(self, entity: ModelType) -> ModelType:
        """Agrega una entidad a la sesión."""
        self.session.add(entity)
        return entity

    async def delete(self, entity: ModelType) -> None:
        """Elimina una entidad de la sesión."""
        await self.session.delete(entity)
