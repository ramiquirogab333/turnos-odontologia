"""Modelos de autenticación (C-03): blacklist de jti para rotación de refresh y logout.

R4: timestamps con zona horaria.
R6: índice en jti.
R13: firmas 100% tipadas.
R14: gestionado vía Alembic 003 (reversible).
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class TokenBlacklist(Base, TimestampMixin):
    """Identificadores de token (jti) revocados para rotación de refresh y logout."""

    __tablename__ = "token_blacklist"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    jti: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        Index("ix_token_blacklist_jti", "jti"),
        Index("ix_token_blacklist_expires_at", "expires_at"),
    )
