"""Tests for BaseRepository and UnitOfWork - Strict TDD."""

import pytest
from app.repositories.base import BaseRepository
from app.repositories.uow import UnitOfWork
from app.models.core import Rol


def test_repository_interface_and_methods():
    assert hasattr(BaseRepository, "get_by_id")
    assert hasattr(BaseRepository, "list_all")
    assert hasattr(BaseRepository, "add")
    assert hasattr(BaseRepository, "delete")


def test_unit_of_work_context_manager():
    assert hasattr(UnitOfWork, "__aenter__")
    assert hasattr(UnitOfWork, "__aexit__")
    assert hasattr(UnitOfWork, "commit")
    assert hasattr(UnitOfWork, "rollback")


@pytest.mark.asyncio
async def test_unit_of_work_lifecycle():
    uow = UnitOfWork()
    async with uow:
        assert uow.session is not None
        # Should rollback without raising error
        await uow.rollback()
