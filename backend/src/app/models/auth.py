"""Modelos de autenticación: sesión del panel en el servidor (C-15; reemplaza la tabla de jti revocados de C-03).

R4: instantes con zona horaria.
R6: índice en la FK ``usuario_id`` y en ``expira_en`` (purga).
R13: firmas 100% tipadas.
R14: gestionado vía Alembic 012 (reversible).
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SesionPanel(Base):
    """Una sesión del panel: ``sid`` viaja en el JWT; el servidor decide si sigue abierta en cada pedido."""

    __tablename__ = "sesion_panel"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sid: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, unique=True)
    usuario_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False)
    #: ``jti`` del único refresh vigente de la sesión (rotación por compare-and-swap).
    refresh_jti: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
    #: Vencimiento absoluto (exclusivo): ningún token de la sesión sirve en ``expira_en`` ni después.
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    renovada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revocada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_revocacion: Mapped[str | None] = mapped_column(Text)
    ip_inicio: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("expira_en > creada_en", name="ck_sesion_panel_expira_despues_de_crear"),
        CheckConstraint(
            "motivo_revocacion IS NULL OR motivo_revocacion IN ('logout', 'usuario_desactivado')",
            name="ck_sesion_panel_motivo"),
        CheckConstraint("(revocada_en IS NULL) = (motivo_revocacion IS NULL)",
                        name="ck_sesion_panel_revocacion_completa"),
        CheckConstraint("ip_inicio IS NULL OR LENGTH(ip_inicio) <= 45", name="ck_sesion_panel_ip_inicio"),
        Index("ix_sesion_panel_usuario_id", "usuario_id"),
        Index("ix_sesion_panel_expira_en", "expira_en"),
    )
