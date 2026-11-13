"""012: sesión del panel en el servidor (C-15; R4, R6, R14).

Crea ``sesion_panel`` (una fila por inicio de sesión: vencimiento absoluto, único refresh vigente y revocación) y
elimina ``token_blacklist``, cuyo único uso era la rotación y el logout que ahora resuelve la sesión (O12). Instantes
en ``TIMESTAMPTZ`` (R4), la FK a ``usuario`` con su índice (R6) y un índice sobre ``expira_en`` para la purga.
``downgrade`` borra ``sesion_panel`` y recrea ``token_blacklist`` vacía, idéntica a la 003 (incluido su índice
redundante). Tras volver atrás conviene rotar ``JWT_SECRET_KEY`` para forzar un nuevo ingreso.

Revision ID: 012_sesion_panel
"""

from typing import Sequence, Union

from alembic import op

revision: str = "012_sesion_panel"
down_revision: Union[str, None] = "011_google_calendar"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE sesion_panel (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            sid UUID NOT NULL UNIQUE,
            usuario_id BIGINT NOT NULL REFERENCES usuario (id) ON DELETE CASCADE,
            refresh_jti UUID NOT NULL,
            creada_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            expira_en TIMESTAMPTZ NOT NULL,
            renovada_en TIMESTAMPTZ,
            revocada_en TIMESTAMPTZ,
            motivo_revocacion TEXT,
            ip_inicio TEXT,
            CONSTRAINT ck_sesion_panel_expira_despues_de_crear CHECK (expira_en > creada_en),
            CONSTRAINT ck_sesion_panel_motivo CHECK (
                motivo_revocacion IS NULL OR motivo_revocacion IN ('logout', 'usuario_desactivado')),
            CONSTRAINT ck_sesion_panel_revocacion_completa CHECK ((revocada_en IS NULL) = (motivo_revocacion IS NULL)),
            CONSTRAINT ck_sesion_panel_ip_inicio CHECK (ip_inicio IS NULL OR LENGTH(ip_inicio) <= 45)
        )
    """)
    op.execute("CREATE INDEX ix_sesion_panel_usuario_id ON sesion_panel (usuario_id)")
    op.execute("CREATE INDEX ix_sesion_panel_expira_en ON sesion_panel (expira_en)")
    op.execute("DROP INDEX IF EXISTS ix_token_blacklist_expires_at")
    op.execute("DROP INDEX IF EXISTS ix_token_blacklist_jti")
    op.execute("DROP TABLE IF EXISTS token_blacklist")


def downgrade() -> None:
    op.execute("""
        CREATE TABLE token_blacklist (
          id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          jti         TEXT NOT NULL UNIQUE
                      CHECK (LENGTH(jti) > 0),
          created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
          expires_at  TIMESTAMPTZ NOT NULL
        )
    """)
    op.execute("CREATE INDEX ix_token_blacklist_jti ON token_blacklist (jti)")
    op.execute("CREATE INDEX ix_token_blacklist_expires_at ON token_blacklist (expires_at)")
    op.execute("DROP INDEX IF EXISTS ix_sesion_panel_expira_en")
    op.execute("DROP INDEX IF EXISTS ix_sesion_panel_usuario_id")
    op.execute("DROP TABLE IF EXISTS sesion_panel")
