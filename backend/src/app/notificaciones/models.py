"""Modelo del recordatorio de WhatsApp (C-09; R4, R6). DDL canónico en la migración 010 (R14)."""

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Index, Integer, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.core import Usuario  # noqa: F401  (resuelve la FK usuario.id en el metadata)
from app.turnos.models import Turno  # noqa: F401  (resuelve la FK turno.id en el metadata)

ESTADOS_RECORDATORIO = ("pendiente", "enviado", "confirmado", "fallido", "anulado")
MOTIVOS_RECORDATORIO = ("sin_telefono", "numero_invalido", "sin_whatsapp", "otro", "error_proveedor",
                        "turno_cancelado", "turno_reprogramado", "turno_iniciado")


class Recordatorio(Base, TimestampMixin):
    """Recordatorio de un turno para un horario concreto (``turno_inicio``). El mensaje no se guarda."""

    __tablename__ = "recordatorio"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    turno_id: Mapped[int] = mapped_column(ForeignKey("turno.id", ondelete="RESTRICT"), nullable=False)
    canal: Mapped[str] = mapped_column(Text, nullable=False, default="whatsapp", server_default="whatsapp")
    estado: Mapped[str] = mapped_column(Text, nullable=False)
    turno_inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    generado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    enviado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enviado_por_usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    confirmado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    intentos_fallidos: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    proximo_intento_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    ultimo_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("canal IN ('whatsapp')", name="ck_recordatorio_canal"),
        CheckConstraint("estado IN ('pendiente', 'enviado', 'confirmado', 'fallido', 'anulado')",
                        name="ck_recordatorio_estado"),
        CheckConstraint(
            "motivo IS NULL OR motivo IN ('sin_telefono', 'numero_invalido', 'sin_whatsapp', 'otro', "
            "'error_proveedor', 'turno_cancelado', 'turno_reprogramado', 'turno_iniciado')",
            name="ck_recordatorio_motivo"),
        CheckConstraint("intentos_fallidos >= 0", name="ck_recordatorio_intentos"),
        CheckConstraint("ultimo_error IS NULL OR LENGTH(ultimo_error) <= 500", name="ck_recordatorio_ultimo_error_len"),
        CheckConstraint("(estado = 'confirmado') = (confirmado_en IS NOT NULL)", name="ck_recordatorio_confirmado"),
        CheckConstraint("estado <> 'enviado' OR enviado_en IS NOT NULL", name="ck_recordatorio_enviado"),
        CheckConstraint("estado NOT IN ('fallido', 'anulado') OR motivo IS NOT NULL",
                        name="ck_recordatorio_motivo_requerido"),
        Index("uq_recordatorio_turno_inicio_vigente", "turno_id", "turno_inicio", unique=True,
              postgresql_where=text("estado <> 'anulado'")),
        Index("ix_recordatorio_proximo_intento", "proximo_intento_en",
              postgresql_where=text("proximo_intento_en IS NOT NULL")),
        Index("ix_recordatorio_listado", "estado", "turno_inicio",
              postgresql_where=text("estado IN ('pendiente', 'fallido')")),
    )
