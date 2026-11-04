"""003: tablas de auth (blacklist de jti para rotación de refresh y logout).

Reversible (R14): upgrade crea token_blacklist, downgrade la elimina.
Tipos tz-aware (R4), índice en cada FK/jti (R6).

Revision ID: 003_auth
down_revision: 002_core_models
"""

from typing import Sequence, Union

from alembic import op

revision: str = "003_auth"
down_revision: Union[str, None] = "002_core_models"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE token_blacklist (
          id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          jti         TEXT NOT NULL UNIQUE
                      CHECK (LENGTH(jti) > 0),
          created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
          expires_at  TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX ix_token_blacklist_jti ON token_blacklist (jti)")
    op.execute("CREATE INDEX ix_token_blacklist_expires_at ON token_blacklist (expires_at)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_token_blacklist_expires_at")
    op.execute("DROP INDEX IF EXISTS ix_token_blacklist_jti")
    op.execute("DROP TABLE IF EXISTS token_blacklist")
