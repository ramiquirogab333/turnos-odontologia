"""004: refuerzo de constraints de catálogo e índices FK (R4, R6, R14).

Refuerza (de forma idempotente) las CHECK constraints del catálogo
(``duracion_minutos > 0``, ``precio_base >= 0``, ``dia_semana BETWEEN 0 AND 6``,
``hora_fin > hora_inicio``) y garantiza índice en cada FK (R6). No crea tablas
(n already existen desde 001/002); solo asegura constraints e índices.

Reversible (R14): ``upgrade`` añade constraints/índices solo si faltan;
``downgrade`` los elimina condicionalmente.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "004_catalogo"
down_revision: Union[str, None] = "003_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _check_exists(name: str, table: str) -> str:
    return (
        f"SELECT 1 FROM pg_constraint "
        f"WHERE conname = '{name}' AND conrelid = '{table}'::regclass"
    )


def _add_check(name: str, table: str, condition: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS ({_check_exists(name, table)}) THEN
                ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({condition});
            END IF;
        END $$;
        """
    )


def upgrade() -> None:
    # --- CHECK constraints del catálogo (idempotentes) ---
    _add_check("ck_tratamiento_duracion_pos", "tratamiento", "duracion_minutos > 0")
    _add_check("ck_tratamiento_precio_no_neg", "tratamiento", "precio_base >= 0")
    _add_check("ck_disponibilidad_dia_semana", "disponibilidad", "dia_semana BETWEEN 0 AND 6")
    _add_check("ck_disponibilidad_horas", "disponibilidad", "hora_fin > hora_inicio")

    # --- Índices en cada FK del catálogo (R6) ---
    op.execute("CREATE INDEX IF NOT EXISTS ix_disponibilidad_profesional_id ON disponibilidad (profesional_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_disponibilidad_sillon_defecto_id ON disponibilidad (sillon_defecto_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_disponibilidad_sillon_defecto_id")
    op.execute("DROP INDEX IF EXISTS ix_disponibilidad_profesional_id")
    op.execute("ALTER TABLE disponibilidad DROP CONSTRAINT IF EXISTS ck_disponibilidad_horas")
    op.execute("ALTER TABLE disponibilidad DROP CONSTRAINT IF EXISTS ck_disponibilidad_dia_semana")
    op.execute("ALTER TABLE tratamiento DROP CONSTRAINT IF EXISTS ck_tratamiento_precio_no_neg")
    op.execute("ALTER TABLE tratamiento DROP CONSTRAINT IF EXISTS ck_tratamiento_duracion_pos")
