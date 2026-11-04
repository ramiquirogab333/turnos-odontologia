"""Base model and reusable mixins (R4, R13)."""

from datetime import datetime
from sqlalchemy import Boolean, DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base declarativa compartida del dominio."""
    pass


class TimestampMixin:
    """Mixin para auditoría temporal con zona horaria estricta (R4)."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        default=func.now(),
    )


class ActiveMixin:
    """Mixin para borrado lógico o estado de activación booleano."""

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        sort_order=999,
    )

    def __init__(self, *args, **kwargs):
        if "is_active" not in kwargs:
            kwargs["is_active"] = True
        super().__init__(*args, **kwargs)
