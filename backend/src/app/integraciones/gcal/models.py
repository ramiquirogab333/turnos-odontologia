"""Modelos de la sincronización con Google Calendar (C-10, D2; R4, R6). DDL canónico en la migración 011 (R14)."""

from datetime import datetime

from sqlalchemy import (BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Identity, Index, Integer, Text,
                        func, text)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.core import Usuario  # noqa: F401  (resuelve la FK usuario.id en el metadata)
from app.turnos.models import Profesional, Turno  # noqa: F401  (resuelve las FK en el metadata)

ESTADOS_CONEXION = ("pendiente", "activa", "revocada", "desconectada")
ESTADOS_EVENTO = ("pendiente", "sincronizado", "borrado", "desvinculado")
TIPOS_CONFLICTO = ("movido_en_google", "borrado_en_google", "solapa_evento_externo")
RESOLUCIONES = ("restaurar_en_google", "desvincular", "revisado", "turno_cancelado", "solape_desaparecido")


class GcalConexion(Base, TimestampMixin):
    """Conexión OAuth de una profesional con su calendario principal. Los tokens se guardan cifrados (O1)."""

    __tablename__ = "gcal_conexion"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    profesional_id: Mapped[int] = mapped_column(ForeignKey("profesional.id", ondelete="RESTRICT"), nullable=False,
                                                unique=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True,
                                                   index=True)
    estado: Mapped[str] = mapped_column(Text, nullable=False)
    cuenta_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    calendario_id: Mapped[str] = mapped_column(Text, nullable=False, default="primary", server_default="primary")
    refresh_token_cifrado: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token_cifrado: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_expira_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    oauth_nonce_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    oauth_verifier_cifrado: Mapped[str | None] = mapped_column(Text, nullable=True)
    oauth_expira_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ultimo_sync_ok_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    proximo_intento_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fallos_consecutivos: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    ultimo_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    conectada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("estado IN ('pendiente', 'activa', 'revocada', 'desconectada')", name="ck_gcal_conexion_estado"),
        CheckConstraint("cuenta_email IS NULL OR LENGTH(cuenta_email) <= 254", name="ck_gcal_conexion_email_len"),
        CheckConstraint("LENGTH(calendario_id) BETWEEN 1 AND 255", name="ck_gcal_conexion_calendario_len"),
        CheckConstraint("refresh_token_cifrado IS NULL OR LENGTH(refresh_token_cifrado) <= 4096",
                        name="ck_gcal_conexion_refresh_len"),
        CheckConstraint("access_token_cifrado IS NULL OR LENGTH(access_token_cifrado) <= 4096",
                        name="ck_gcal_conexion_access_len"),
        CheckConstraint("oauth_verifier_cifrado IS NULL OR LENGTH(oauth_verifier_cifrado) <= 4096",
                        name="ck_gcal_conexion_verifier_len"),
        CheckConstraint("sync_token IS NULL OR LENGTH(sync_token) <= 2048", name="ck_gcal_conexion_sync_token_len"),
        CheckConstraint("fallos_consecutivos >= 0", name="ck_gcal_conexion_fallos"),
        CheckConstraint("ultimo_error IS NULL OR LENGTH(ultimo_error) <= 300", name="ck_gcal_conexion_error_len"),
        CheckConstraint("estado <> 'activa' OR refresh_token_cifrado IS NOT NULL", name="ck_gcal_conexion_activa_token"),
        CheckConstraint("estado <> 'pendiente' OR (oauth_nonce_hash IS NOT NULL AND oauth_expira_en IS NOT NULL)",
                        name="ck_gcal_conexion_pendiente_state"),
        Index("ix_gcal_conexion_trabajo", "proximo_intento_en", postgresql_where=text("estado = 'activa'")),
    )


class EventoCalendar(Base, TimestampMixin):
    """Vínculo ``Turno <-> evento de Google`` (origen sistema) o franja ocupada ajena (origen google, O16, O19)."""

    __tablename__ = "evento_calendar"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    conexion_id: Mapped[int] = mapped_column(ForeignKey("gcal_conexion.id", ondelete="RESTRICT"), nullable=False)
    turno_id: Mapped[int | None] = mapped_column(ForeignKey("turno.id", ondelete="RESTRICT"), nullable=True,
                                                 index=True)
    origen: Mapped[str] = mapped_column(Text, nullable=False)
    google_event_id: Mapped[str] = mapped_column(Text, nullable=False)
    estado: Mapped[str] = mapped_column(Text, nullable=False)
    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fin: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ocupa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    etag: Mapped[str | None] = mapped_column(Text, nullable=True)
    hash_contenido: Mapped[str | None] = mapped_column(Text, nullable=True)
    generacion: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    __table_args__ = (
        CheckConstraint("origen IN ('sistema', 'google')", name="ck_evento_calendar_origen"),
        CheckConstraint("estado IN ('pendiente', 'sincronizado', 'borrado', 'desvinculado')",
                        name="ck_evento_calendar_estado"),
        CheckConstraint("LENGTH(google_event_id) BETWEEN 5 AND 1024", name="ck_evento_calendar_google_id_len"),
        CheckConstraint("fin > inicio", name="ck_evento_calendar_fin_after_inicio"),
        CheckConstraint("etag IS NULL OR LENGTH(etag) <= 255", name="ck_evento_calendar_etag_len"),
        CheckConstraint("hash_contenido IS NULL OR LENGTH(hash_contenido) <= 64", name="ck_evento_calendar_hash_len"),
        CheckConstraint("generacion >= 0", name="ck_evento_calendar_generacion"),
        CheckConstraint("(origen = 'sistema') = (turno_id IS NOT NULL)", name="ck_evento_calendar_origen_turno"),
        Index("uq_evento_calendar_conexion_google_id", "conexion_id", "google_event_id", unique=True),
        Index("uq_evento_calendar_vigente", "conexion_id", "turno_id", unique=True,
              postgresql_where=text("origen = 'sistema' AND estado IN ('pendiente', 'sincronizado')")),
    )


class GcalConflicto(Base):
    """Desacuerdo entre un turno y Google Calendar, a resolver a mano (RN-GC-02)."""

    __tablename__ = "gcal_conflicto"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    conexion_id: Mapped[int] = mapped_column(ForeignKey("gcal_conexion.id", ondelete="RESTRICT"), nullable=False)
    turno_id: Mapped[int] = mapped_column(ForeignKey("turno.id", ondelete="RESTRICT"), nullable=False, index=True)
    evento_id: Mapped[int] = mapped_column(ForeignKey("evento_calendar.id", ondelete="RESTRICT"), nullable=False,
                                           index=True)
    tipo: Mapped[str] = mapped_column(Text, nullable=False)
    estado: Mapped[str] = mapped_column(Text, nullable=False, default="abierto", server_default="abierto")
    sistema_inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sistema_fin: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    google_inicio: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    google_fin: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolucion: Mapped[str | None] = mapped_column(Text, nullable=True)
    resuelto_por_usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    detectado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    resuelto_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("tipo IN ('movido_en_google', 'borrado_en_google', 'solapa_evento_externo')",
                        name="ck_gcal_conflicto_tipo"),
        CheckConstraint("estado IN ('abierto', 'resuelto')", name="ck_gcal_conflicto_estado"),
        CheckConstraint("resolucion IS NULL OR resolucion IN ('restaurar_en_google', 'desvincular', 'revisado', "
                        "'turno_cancelado', 'solape_desaparecido')", name="ck_gcal_conflicto_resolucion"),
        CheckConstraint("(estado = 'resuelto') = (resolucion IS NOT NULL) AND (estado = 'resuelto') = (resuelto_en IS NOT NULL)",
                        name="ck_gcal_conflicto_resuelto"),
        Index("uq_gcal_conflicto_abierto", "evento_id", "turno_id", "tipo", unique=True,
              postgresql_where=text("estado = 'abierto'")),
        Index("ix_gcal_conflicto_listado", "conexion_id", "estado"),
    )
