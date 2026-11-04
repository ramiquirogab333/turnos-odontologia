"""002: core models — ObraSocial, Paciente, Rol, Usuario, UsuarioRol, Disponibilidad, Nomenclador, RegistroAuditoria + Turno.paciente_id.

Reversible (R14): downgrade drops the paciente_id column, indexes, and tables in reverse order.
Conserva la extensión btree_gist (compartida con 001).

Revision ID: 002_core_models
"""

from typing import Sequence, Union

from alembic import op

revision: str = "002_core_models"
down_revision: Union[str, None] = "001_create_agenda"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Tabla rol ---
    op.execute(
        """
        CREATE TABLE rol (
          id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          nombre      TEXT NOT NULL UNIQUE
                      CHECK (nombre IN ('admin', 'odontologo', 'recepcion')),
          descripcion TEXT NOT NULL DEFAULT ''
                      CHECK (LENGTH(descripcion) BETWEEN 0 AND 200)
        )
        """
    )

    # --- Tabla obra_social ---
    op.execute(
        """
        CREATE TABLE obra_social (
          id      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          codigo  TEXT NOT NULL UNIQUE
                  CHECK (LENGTH(codigo) BETWEEN 2 AND 30),
          nombre  TEXT NOT NULL
                  CHECK (LENGTH(nombre) BETWEEN 2 AND 120),
          sigla   TEXT NOT NULL DEFAULT ''
                  CHECK (LENGTH(sigla) BETWEEN 0 AND 10),
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          is_active BOOLEAN NOT NULL DEFAULT true
        )
        """
    )

    # --- Tabla usuario (FK a profesional, existente en 001) ---
    op.execute(
        """
        CREATE TABLE usuario (
          id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          email          TEXT NOT NULL UNIQUE
                         CHECK (LENGTH(email) BETWEEN 5 AND 120),
          nombre_completo TEXT NOT NULL
                          CHECK (LENGTH(nombre_completo) BETWEEN 2 AND 120),
          hashed_password TEXT NOT NULL,
          profesional_id BIGINT REFERENCES profesional (id) ON DELETE SET NULL,
          created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
          is_active      BOOLEAN NOT NULL DEFAULT true
        )
        """
    )
    op.execute("CREATE INDEX ix_usuario_profesional_id ON usuario (profesional_id)")

    # --- Tabla paciente (FK a obra_social) ---
    op.execute(
        """
        CREATE TABLE paciente (
          id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          nombre         TEXT NOT NULL
                         CHECK (LENGTH(nombre) BETWEEN 1 AND 100),
          apellido       TEXT NOT NULL
                         CHECK (LENGTH(apellido) BETWEEN 1 AND 100),
          dni            TEXT NOT NULL UNIQUE
                         CHECK (dni ~ '^[0-9]{7,8}$'),
          telefono       TEXT NOT NULL
                         CHECK (LENGTH(telefono) BETWEEN 8 AND 25),
          email          TEXT
                         CHECK (LENGTH(email) BETWEEN 5 AND 120),
          obra_social_id BIGINT REFERENCES obra_social (id) ON DELETE SET NULL,
          numero_afiliado TEXT,
          created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
          is_active      BOOLEAN NOT NULL DEFAULT true
        )
        """
    )
    op.execute("CREATE INDEX ix_paciente_obra_social_id ON paciente (obra_social_id)")

    # --- Tabla usuario_rol (FK a usuario, rol) ---
    op.execute(
        """
        CREATE TABLE usuario_rol (
          id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          usuario_id BIGINT NOT NULL REFERENCES usuario (id) ON DELETE CASCADE,
          rol_id    BIGINT NOT NULL REFERENCES rol (id) ON DELETE CASCADE,
          UNIQUE (usuario_id, rol_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_usuario_rol_usuario_id ON usuario_rol (usuario_id)")
    op.execute("CREATE INDEX ix_usuario_rol_rol_id ON usuario_rol (rol_id)")

    # --- Tabla disponibilidad (FK a profesional, sillon) ---
    op.execute(
        """
        CREATE TABLE disponibilidad (
          id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          profesional_id    BIGINT NOT NULL REFERENCES profesional (id) ON DELETE CASCADE,
          dia_semana        INTEGER NOT NULL
                            CHECK (dia_semana BETWEEN 0 AND 6),
          hora_inicio       TIME NOT NULL,
          hora_fin          TIME NOT NULL
                            CHECK (hora_fin > hora_inicio),
          sillon_defecto_id BIGINT REFERENCES sillon (id) ON DELETE SET NULL,
          created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
          is_active         BOOLEAN NOT NULL DEFAULT true
        )
        """
    )
    op.execute("CREATE INDEX ix_disponibilidad_profesional_id ON disponibilidad (profesional_id)")
    op.execute("CREATE INDEX ix_disponibilidad_sillon_defecto_id ON disponibilidad (sillon_defecto_id)")

    # --- Tabla nomenclador (FK a obra_social, tratamiento) ---
    op.execute(
        """
        CREATE TABLE nomenclador (
          id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          obra_social_id     BIGINT NOT NULL REFERENCES obra_social (id) ON DELETE CASCADE,
          tratamiento_id     BIGINT NOT NULL REFERENCES tratamiento (id) ON DELETE CASCADE,
          codigo_prestacion  TEXT NOT NULL,
          cobertura_porcentaje NUMERIC(5, 2) NOT NULL DEFAULT 100.00
                               CHECK (cobertura_porcentaje BETWEEN 0 AND 100),
          arancel_diferencial NUMERIC(10, 2) NOT NULL DEFAULT 0.00
                               CHECK (arancel_diferencial >= 0),
          UNIQUE (obra_social_id, tratamiento_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_nomenclador_obra_social_id ON nomenclador (obra_social_id)")
    op.execute("CREATE INDEX ix_nomenclador_tratamiento_id ON nomenclador (tratamiento_id)")

    # --- Tabla registro_auditoria (FK a usuario) ---
    op.execute(
        """
        CREATE TABLE registro_auditoria (
          id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          usuario_id   BIGINT REFERENCES usuario (id) ON DELETE SET NULL,
          accion       TEXT NOT NULL
                       CHECK (LENGTH(accion) BETWEEN 2 AND 50),
          entidad      TEXT NOT NULL
                       CHECK (LENGTH(entidad) BETWEEN 2 AND 50),
          entidad_id   TEXT,
          datos_antes  JSONB,
          datos_despues JSONB,
          ip           TEXT,
          created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_registro_auditoria_usuario_id ON registro_auditoria (usuario_id)")
    op.execute("CREATE INDEX ix_registro_auditoria_created_at ON registro_auditoria (created_at)")

    # --- Turno: añadir paciente_id (nullable inicialmente, Decision 5 del design.md) ---
    op.execute("ALTER TABLE turno ADD COLUMN paciente_id BIGINT REFERENCES paciente (id) ON DELETE RESTRICT")
    op.execute("CREATE INDEX ix_turno_paciente_id ON turno (paciente_id)")
    op.execute("CREATE INDEX ix_turno_paciente_inicio ON turno (paciente_id, inicio)")
    op.execute("CREATE INDEX ix_turno_estado ON turno (estado)")


def downgrade() -> None:
    # Revertir índices y columna de turno
    op.execute("DROP INDEX IF EXISTS ix_turno_estado")
    op.execute("DROP INDEX IF EXISTS ix_turno_paciente_inicio")
    op.execute("DROP INDEX IF EXISTS ix_turno_paciente_id")
    op.execute("ALTER TABLE turno DROP COLUMN IF EXISTS paciente_id")

    # Drop tablas en orden inverso (hijos antes que padres)
    op.execute("DROP TABLE IF EXISTS registro_auditoria")
    op.execute("DROP TABLE IF EXISTS nomenclador")
    op.execute("DROP TABLE IF EXISTS disponibilidad")
    op.execute("DROP TABLE IF EXISTS usuario_rol")
    op.execute("DROP TABLE IF EXISTS paciente")
    op.execute("DROP TABLE IF EXISTS usuario")
    op.execute("DROP TABLE IF EXISTS obra_social")
    op.execute("DROP TABLE IF EXISTS rol")
    # btree_gist se conserva: compartida con 001.
