"""Async Unit of Work managing transactions and session lifecycles (R13, R16)."""

from types import TracebackType
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.db import get_session_factory


class UnitOfWork:
    """Async Unit of Work para control transaccional atómico."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self.session_factory = session_factory or get_session_factory()
        self.session: AsyncSession | None = None

    async def __aenter__(self) -> "UnitOfWork":
        self.session = self.session_factory()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self.session is None:
            return
        if exc_type is not None:
            await self.rollback()
        await self.session.close()

    async def commit(self) -> None:
        """Confirma la transacción actual."""
        if self.session is not None:
            await self.session.commit()

    async def rollback(self) -> None:
        """Revierte la transacción actual."""
        if self.session is not None:
            await self.session.rollback()
