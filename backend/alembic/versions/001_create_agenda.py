"""001: fundar agenda — Profesional/Sillon/Tratamiento/Turno + 2 EXCLUDE parciales.

Garantía anti-solape (R5): dos ``EXCLUDE USING gist`` parciales sobre
``turno`` — uno por profesional y otro por sillón — cubriendo solo estados
bloqueantes (``reservado``, ``confirmado``). Reversible (R14): el downgrade
dropea constraints, índices y tablas en orden inverso pero conserva la
extensión ``btree_gist`` (compartida con futuras migraciones).

Revision ID: 001_create_agenda
"""

from typing import Sequence, Union

from alembic import op

revision: str = "001_create_agenda"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.execute(
        """
        CREATE TABLE profesional (
          id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          nombre       TEXT NOT NULL CHECK (LENGTH(nombre) BETWEEN 1 AND 120),
          matricula    TEXT NOT NULL CHECK (LENGTH(matricula) BETWEEN 1 AND 40),
          especialidad TEXT NOT NULL DEFAULT '' CHECK (LENGTH(especialidad) <= 120)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE sillon (
          id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          nombre TEXT NOT NULL CHECK (LENGTH(nombre) BETWEEN 1 AND 60),
          estado TEXT NOT NULL DEFAULT 'activo'
                 CHECK (estado IN ('activo', 'inactivo', 'mantenimiento'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE tratamiento (
          id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          nombre           TEXT NOT NULL CHECK (LENGTH(nombre) BETWEEN 1 AND 120),
          duracion_minutos INTEGER NOT NULL CHECK (duracion_minutos > 0),
          precio_base      NUMERIC(10, 2) NOT NULL CHECK (precio_base >= 0)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE turno (
          id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          profesional_id BIGINT NOT NULL REFERENCES profesional (id) ON DELETE RESTRICT,
          sillon_id      BIGINT NOT NULL REFERENCES sillon (id) ON DELETE RESTRICT,
          tratamiento_id BIGINT NOT NULL REFERENCES tratamiento (id) ON DELETE RESTRICT,
          inicio         TIMESTAMPTZ NOT NULL,
          fin            TIMESTAMPTZ NOT NULL CHECK (fin > inicio),
          estado         TEXT NOT NULL DEFAULT 'reservado'
                         CHECK (estado IN ('reservado', 'confirmado', 'en_espera',
                                           'cancelado', 'ausente', 'atendido')),
          periodo        tstzrange GENERATED ALWAYS AS (tstzrange(inicio, fin, '[)')) STORED
        )
        """
    )

    op.execute("CREATE INDEX ON turno (profesional_id)")
    op.execute("CREATE INDEX ON turno (sillon_id)")
    op.execute("CREATE INDEX ON turno (tratamiento_id)")
    op.execute("CREATE INDEX ix_turno_profesional_inicio ON turno (profesional_id, inicio)")
    op.execute("CREATE INDEX ix_turno_sillon_inicio ON turno (sillon_id, inicio)")

    op.execute(
        """
        ALTER TABLE turno ADD CONSTRAINT turno_no_solape_profesional
          EXCLUDE USING gist (profesional_id WITH =, periodo WITH &&)
          WHERE (estado IN ('reservado', 'confirmado'))
        """
    )
    op.execute(
        """
        ALTER TABLE turno ADD CONSTRAINT turno_no_solape_sillon
          EXCLUDE USING gist (sillon_id WITH =, periodo WITH &&)
          WHERE (estado IN ('reservado', 'confirmado'))
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE turno DROP CONSTRAINT IF EXISTS turno_no_solape_sillon")
    op.execute("ALTER TABLE turno DROP CONSTRAINT IF EXISTS turno_no_solape_profesional")
    op.execute("DROP INDEX IF EXISTS ix_turno_sillon_inicio")
    op.execute("DROP INDEX IF EXISTS ix_turno_profesional_inicio")
    op.execute("DROP TABLE IF EXISTS turno")
    op.execute("DROP TABLE IF EXISTS tratamiento")
    op.execute("DROP TABLE IF EXISTS sillon")
    op.execute("DROP TABLE IF EXISTS profesional")
    # btree_gist se conserva a propósito: es compartida con futuras migraciones.
