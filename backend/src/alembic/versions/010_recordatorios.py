"""010: recordatorios de turnos por WhatsApp manual (C-09; R4, R6, R14).

Tabla ``recordatorio``: un registro por turno y horario de inicio (``turno_inicio`` es la foto del horario que se
recuerda). El mensaje NO se guarda (PII, siempre recalculable). Un índice único parcial garantiza un solo
recordatorio vigente (no ``anulado``) por turno y horario aunque corran varios workers.

Instantes en ``TIMESTAMPTZ``, textos con ``CHECK``, toda FK con su índice (R4, R6). ``downgrade`` borra la tabla y con
ella el historial de recordatorios (los turnos no se tocan).

Revision ID: 010_recordatorios
"""

from typing import Sequence, Union

from alembic import op

revision: str = "010_recordatorios"
down_revision: Union[str, None] = "009_caja_cierres_devol"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE recordatorio (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            turno_id BIGINT NOT NULL REFERENCES turno (id) ON DELETE RESTRICT,
            canal TEXT NOT NULL DEFAULT 'whatsapp',
            estado TEXT NOT NULL,
            turno_inicio TIMESTAMPTZ NOT NULL,
            generado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            enviado_en TIMESTAMPTZ,
            enviado_por_usuario_id BIGINT REFERENCES usuario (id) ON DELETE SET NULL,
            confirmado_en TIMESTAMPTZ,
            intentos_fallidos INTEGER NOT NULL DEFAULT 0,
            proximo_intento_en TIMESTAMPTZ,
            motivo TEXT,
            ultimo_error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_recordatorio_canal CHECK (canal IN ('whatsapp')),
            CONSTRAINT ck_recordatorio_estado CHECK (
                estado IN ('pendiente', 'enviado', 'confirmado', 'fallido', 'anulado')),
            CONSTRAINT ck_recordatorio_motivo CHECK (motivo IS NULL OR motivo IN (
                'sin_telefono', 'numero_invalido', 'sin_whatsapp', 'otro', 'error_proveedor',
                'turno_cancelado', 'turno_reprogramado', 'turno_iniciado')),
            CONSTRAINT ck_recordatorio_intentos CHECK (intentos_fallidos >= 0),
            CONSTRAINT ck_recordatorio_ultimo_error_len CHECK (ultimo_error IS NULL OR LENGTH(ultimo_error) <= 500),
            CONSTRAINT ck_recordatorio_confirmado CHECK ((estado = 'confirmado') = (confirmado_en IS NOT NULL)),
            CONSTRAINT ck_recordatorio_enviado CHECK (estado <> 'enviado' OR enviado_en IS NOT NULL),
            CONSTRAINT ck_recordatorio_motivo_requerido CHECK (
                estado NOT IN ('fallido', 'anulado') OR motivo IS NOT NULL)
        )
    """)
    # Un solo recordatorio vigente por horario del turno; también indexa la FK turno_id (R6).
    op.execute("CREATE UNIQUE INDEX uq_recordatorio_turno_inicio_vigente ON recordatorio (turno_id, turno_inicio) "
               "WHERE estado <> 'anulado'")
    op.execute("CREATE INDEX ix_recordatorio_enviado_por_usuario_id ON recordatorio (enviado_por_usuario_id)")
    op.execute("CREATE INDEX ix_recordatorio_proximo_intento ON recordatorio (proximo_intento_en) "
               "WHERE proximo_intento_en IS NOT NULL")
    op.execute("CREATE INDEX ix_recordatorio_listado ON recordatorio (estado, turno_inicio) "
               "WHERE estado IN ('pendiente', 'fallido')")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS recordatorio")
