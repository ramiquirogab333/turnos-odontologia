"""Tests for base mixins (TimestampMixin, ActiveMixin) - Strict TDD."""

from datetime import datetime, timezone
import pytest
from sqlalchemy import BigInteger, Identity
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.models.base import ActiveMixin, TimestampMixin


class DummyBase(DeclarativeBase):
    pass


class DummyItem(TimestampMixin, ActiveMixin, DummyBase):
    __tablename__ = "dummy_item"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)


def test_mixins_columns_exist_and_defaults():
    item = DummyItem()
    # is_active default
    assert item.is_active is True
    # Column types
    assert DummyItem.created_at.type.timezone is True
    assert DummyItem.updated_at.type.timezone is True
    assert DummyItem.is_active.nullable is False


def test_active_mixin_can_be_set_to_false():
    item = DummyItem(is_active=False)
    assert item.is_active is False


def test_timestamp_mixin_metadata():
    assert DummyItem.created_at.name == "created_at"
    assert DummyItem.updated_at.name == "updated_at"
    assert DummyItem.created_at.nullable is False
    assert DummyItem.updated_at.nullable is False
    assert DummyItem.created_at.server_default is not None
    assert DummyItem.updated_at.server_default is not None
