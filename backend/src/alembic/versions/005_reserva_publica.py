"""005: reserva pública - código de gestión y contacto en turno (C-05; R4, R6, R14).

Agrega a ``turno`` las columnas ``codigo_gestion`` (UNIQUE, índice implícito),
``contacto_nombre`` y ``contacto_telefono`` (E.164), todas NULL para los turnos
internos. La reserva pública no crea ``paciente`` (exige DNI, RN-TU-06).

Reversible (R14): ``downgrade`` elimina constraints y columnas.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "005_reserva_publica"
down_revision: Union[str, None] = "004_catalogo"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE turno ADD COLUMN IF NOT EXISTS codigo_gestion TEXT")
    op.execute("ALTER TABLE turno ADD COLUMN IF NOT EXISTS contacto_nombre TEXT")
    op.execute("ALTER TABLE turno ADD COLUMN IF NOT EXISTS contacto_telefono TEXT")
    op.execute(
        "ALTER TABLE turno ADD CONSTRAINT turno_codigo_gestion_key UNIQUE (codigo_gestion)"
    )
    op.execute(
        "ALTER TABLE turno ADD CONSTRAINT ck_turno_codigo_gestion_len "
        "CHECK (codigo_gestion IS NULL OR LENGTH(codigo_gestion) BETWEEN 8 AND 64)"
    )
    op.execute(
        "ALTER TABLE turno ADD CONSTRAINT ck_turno_contacto_nombre_len "
        "CHECK (contacto_nombre IS NULL OR LENGTH(contacto_nombre) BETWEEN 1 AND 200)"
    )
    op.execute(
        "ALTER TABLE turno ADD CONSTRAINT ck_turno_contacto_telefono_e164 "
        r"CHECK (contacto_telefono IS NULL OR contacto_telefono ~ '^\+[1-9][0-9]{1,14}$')"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE turno DROP CONSTRAINT IF EXISTS ck_turno_contacto_telefono_e164")
    op.execute("ALTER TABLE turno DROP CONSTRAINT IF EXISTS ck_turno_contacto_nombre_len")
    op.execute("ALTER TABLE turno DROP CONSTRAINT IF EXISTS ck_turno_codigo_gestion_len")
    op.execute("ALTER TABLE turno DROP CONSTRAINT IF EXISTS turno_codigo_gestion_key")
    op.execute("ALTER TABLE turno DROP COLUMN IF EXISTS contacto_telefono")
    op.execute("ALTER TABLE turno DROP COLUMN IF EXISTS contacto_nombre")
    op.execute("ALTER TABLE turno DROP COLUMN IF EXISTS codigo_gestion")
