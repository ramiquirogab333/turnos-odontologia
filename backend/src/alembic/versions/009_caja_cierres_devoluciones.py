"""009: cierre de caja, devoluciones de la seña y búsqueda sin acentos (C-12; R4, R6, R14).

- ``cierre_caja`` y ``cierre_caja_linea``: foto inmutable de la caja de un día terminado (un vigente por día).
- ``pago_sena`` y ``pago_sena_aprobacion``: estado ``reembolsado`` con su fecha, usuario y referencia.
- Relleno: todo ``a_reembolsar`` sin ``acreditado_en`` lo recibe de ``updated_at`` (la caja necesita el instante).
- Extensión ``unaccent`` para el listado de pacientes.

Dinero en ``NUMERIC``, instantes en ``TIMESTAMPTZ``, textos con ``CHECK``, toda FK con su índice (R4, R6). ``downgrade``
es completo: devuelve los ``reembolsado`` a ``a_reembolsar`` y pierde los cierres y los datos de devolución.

Revision ID: 009_caja_cierres_devol (id acortado: alembic_version.version_num es VARCHAR(32))
"""

from typing import Sequence, Union

from alembic import op

revision: str = "009_caja_cierres_devol"
down_revision: Union[str, None] = "008_ficha_odonto_presup"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ESTADOS_ANTERIORES = "'pendiente', 'acreditado', 'vencido', 'no_reembolsado', 'a_reembolsar', 'en_revision'"
ESTADOS_NUEVOS = ESTADOS_ANTERIORES + ", 'reembolsado'"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")

    op.execute("""
        CREATE TABLE cierre_caja (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            dia DATE NOT NULL,
            estado TEXT NOT NULL DEFAULT 'vigente',
            total_ingresos NUMERIC(14, 2) NOT NULL,
            total_egresos NUMERIC(14, 2) NOT NULL,
            total_neto NUMERIC(14, 2) NOT NULL,
            observaciones TEXT,
            cerrado_por BIGINT REFERENCES usuario (id) ON DELETE SET NULL,
            cerrado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            anulado_por BIGINT REFERENCES usuario (id) ON DELETE SET NULL,
            anulado_en TIMESTAMPTZ,
            anulado_motivo TEXT,
            CONSTRAINT ck_cierre_caja_estado CHECK (estado IN ('vigente', 'anulado')),
            CONSTRAINT ck_cierre_caja_totales CHECK (total_ingresos >= 0 AND total_egresos >= 0),
            CONSTRAINT ck_cierre_caja_neto CHECK (total_neto = total_ingresos - total_egresos),
            CONSTRAINT ck_cierre_caja_observaciones_len CHECK (observaciones IS NULL OR LENGTH(observaciones) <= 500),
            CONSTRAINT ck_cierre_caja_anulado_motivo_len CHECK (
                anulado_motivo IS NULL OR LENGTH(anulado_motivo) BETWEEN 3 AND 300),
            CONSTRAINT ck_cierre_caja_anulacion CHECK (
                (estado = 'vigente' AND anulado_en IS NULL AND anulado_motivo IS NULL AND anulado_por IS NULL)
                OR (estado = 'anulado' AND anulado_en IS NOT NULL AND anulado_motivo IS NOT NULL))
        )
    """)
    op.execute("CREATE UNIQUE INDEX uq_cierre_caja_dia_vigente ON cierre_caja (dia) WHERE estado = 'vigente'")
    op.execute("CREATE INDEX ix_cierre_caja_dia ON cierre_caja (dia)")
    op.execute("CREATE INDEX ix_cierre_caja_cerrado_por ON cierre_caja (cerrado_por)")
    op.execute("CREATE INDEX ix_cierre_caja_anulado_por ON cierre_caja (anulado_por)")

    op.execute("""
        CREATE TABLE cierre_caja_linea (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            cierre_id BIGINT NOT NULL REFERENCES cierre_caja (id) ON DELETE RESTRICT,
            concepto TEXT NOT NULL,
            medio TEXT NOT NULL,
            cantidad INTEGER NOT NULL,
            total NUMERIC(14, 2) NOT NULL,
            CONSTRAINT uq_cierre_caja_linea UNIQUE (cierre_id, concepto, medio),
            CONSTRAINT ck_cierre_caja_linea_concepto CHECK (concepto IN ('sena', 'pago_presupuesto', 'devolucion_sena')),
            CONSTRAINT ck_cierre_caja_linea_medio CHECK (medio IN ('mercadopago', 'transferencia')),
            CONSTRAINT ck_cierre_caja_linea_cantidad CHECK (cantidad >= 0),
            CONSTRAINT ck_cierre_caja_linea_total CHECK (total >= 0)
        )
    """)

    # Inmutabilidad (D3, capa 3): solo UPDATE; el DELETE queda libre para la limpieza de los tests (ninguna ruta borra).
    op.execute("""
        CREATE FUNCTION fn_cierre_caja_linea_inmutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'las líneas de un cierre de caja no se modifican (C-12)' USING ERRCODE = 'check_violation';
        END;
        $$
    """)
    op.execute("CREATE TRIGGER trg_cierre_caja_linea_inmutable BEFORE UPDATE ON cierre_caja_linea "
               "FOR EACH ROW EXECUTE FUNCTION fn_cierre_caja_linea_inmutable()")
    # Solo se permite vigente -> anulado (con sus campos). Quién cerró o anuló puede pasar a NULL: es el efecto de
    # ``ON DELETE SET NULL`` cuando se borra un usuario; cambiarlo a otro usuario no.
    op.execute("""
        CREATE FUNCTION fn_cierre_caja_inmutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.id IS DISTINCT FROM OLD.id OR NEW.dia IS DISTINCT FROM OLD.dia
               OR NEW.total_ingresos IS DISTINCT FROM OLD.total_ingresos
               OR NEW.total_egresos IS DISTINCT FROM OLD.total_egresos
               OR NEW.total_neto IS DISTINCT FROM OLD.total_neto
               OR NEW.observaciones IS DISTINCT FROM OLD.observaciones
               OR NEW.cerrado_en IS DISTINCT FROM OLD.cerrado_en
               OR (NEW.cerrado_por IS DISTINCT FROM OLD.cerrado_por AND NEW.cerrado_por IS NOT NULL)
               OR (OLD.estado = 'anulado' AND (NEW.estado <> 'anulado'
                    OR NEW.anulado_en IS DISTINCT FROM OLD.anulado_en
                    OR NEW.anulado_motivo IS DISTINCT FROM OLD.anulado_motivo
                    OR (NEW.anulado_por IS DISTINCT FROM OLD.anulado_por AND NEW.anulado_por IS NOT NULL)))
            THEN
                RAISE EXCEPTION 'un cierre de caja no se modifica; solo se anula (C-12)' USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("CREATE TRIGGER trg_cierre_caja_inmutable BEFORE UPDATE ON cierre_caja "
               "FOR EACH ROW EXECUTE FUNCTION fn_cierre_caja_inmutable()")

    # Devoluciones de la seña (D5).
    op.execute("ALTER TABLE pago_sena DROP CONSTRAINT pago_sena_estado_check")
    op.execute(f"ALTER TABLE pago_sena ADD CONSTRAINT pago_sena_estado_check CHECK (estado IN ({ESTADOS_NUEVOS}))")
    op.execute("ALTER TABLE pago_sena ADD COLUMN reembolsado_en TIMESTAMPTZ NULL")
    op.execute("ALTER TABLE pago_sena ADD COLUMN reembolsado_por_usuario_id BIGINT NULL "
               "REFERENCES usuario (id) ON DELETE RESTRICT")
    op.execute("ALTER TABLE pago_sena ADD COLUMN reembolso_referencia TEXT NULL")
    op.execute("ALTER TABLE pago_sena ADD CONSTRAINT ck_pago_sena_reembolso_ref_len CHECK ("
               "reembolso_referencia IS NULL OR LENGTH(reembolso_referencia) BETWEEN 3 AND 64)")
    op.execute("ALTER TABLE pago_sena ADD CONSTRAINT ck_pago_sena_reembolso CHECK ("
               "(estado = 'reembolsado' AND reembolsado_en IS NOT NULL AND reembolso_referencia IS NOT NULL) "
               "OR (estado <> 'reembolsado' AND reembolsado_en IS NULL AND reembolso_referencia IS NULL))")
    op.execute("CREATE INDEX ix_pago_sena_reembolsado_por ON pago_sena (reembolsado_por_usuario_id)")
    op.execute("CREATE INDEX ix_pago_sena_acreditado_en ON pago_sena (acreditado_en) WHERE acreditado_en IS NOT NULL")
    op.execute("CREATE INDEX ix_pago_sena_reembolsado_en ON pago_sena (reembolsado_en) WHERE estado = 'reembolsado'")
    op.execute("CREATE INDEX ix_pago_sena_por_resolver ON pago_sena (estado) "
               "WHERE estado IN ('a_reembolsar', 'en_revision')")

    op.execute("ALTER TABLE pago_sena_aprobacion DROP CONSTRAINT pago_sena_aprobacion_estado_check")
    op.execute("ALTER TABLE pago_sena_aprobacion ADD CONSTRAINT pago_sena_aprobacion_estado_check "
               "CHECK (estado IN ('aplicado', 'en_revision', 'a_reembolsar', 'reembolsado'))")
    op.execute("ALTER TABLE pago_sena_aprobacion ADD COLUMN reembolsado_en TIMESTAMPTZ NULL")
    op.execute("ALTER TABLE pago_sena_aprobacion ADD COLUMN reembolsado_por_usuario_id BIGINT NULL "
               "REFERENCES usuario (id) ON DELETE RESTRICT")
    op.execute("ALTER TABLE pago_sena_aprobacion ADD COLUMN reembolso_referencia TEXT NULL")
    op.execute("ALTER TABLE pago_sena_aprobacion ADD CONSTRAINT ck_pago_sena_aprobacion_reembolso_ref_len CHECK ("
               "reembolso_referencia IS NULL OR LENGTH(reembolso_referencia) BETWEEN 3 AND 64)")
    op.execute("ALTER TABLE pago_sena_aprobacion ADD CONSTRAINT ck_pago_sena_aprobacion_reembolso CHECK ("
               "(estado = 'reembolsado' AND reembolsado_en IS NOT NULL AND reembolso_referencia IS NOT NULL) "
               "OR (estado <> 'reembolsado' AND reembolsado_en IS NULL AND reembolso_referencia IS NULL))")
    op.execute("CREATE INDEX ix_pago_sena_aprobacion_reembolsado_por "
               "ON pago_sena_aprobacion (reembolsado_por_usuario_id)")

    # Relleno: todo a_reembolsar necesita el instante en que la clínica recibió el dinero.
    op.execute("UPDATE pago_sena SET acreditado_en = updated_at WHERE estado = 'a_reembolsar' AND acreditado_en IS NULL")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_cierre_caja_inmutable ON cierre_caja")
    op.execute("DROP TRIGGER IF EXISTS trg_cierre_caja_linea_inmutable ON cierre_caja_linea")
    op.execute("DROP TABLE IF EXISTS cierre_caja_linea")
    op.execute("DROP TABLE IF EXISTS cierre_caja")
    op.execute("DROP FUNCTION IF EXISTS fn_cierre_caja_inmutable()")
    op.execute("DROP FUNCTION IF EXISTS fn_cierre_caja_linea_inmutable()")

    # Los reembolsados vuelven a estar por devolver (se pierden su fecha, usuario y referencia).
    op.execute("ALTER TABLE pago_sena_aprobacion DROP CONSTRAINT ck_pago_sena_aprobacion_reembolso")
    op.execute("ALTER TABLE pago_sena_aprobacion DROP CONSTRAINT ck_pago_sena_aprobacion_reembolso_ref_len")
    op.execute("ALTER TABLE pago_sena_aprobacion DROP CONSTRAINT pago_sena_aprobacion_estado_check")
    op.execute("UPDATE pago_sena_aprobacion SET estado = 'a_reembolsar' WHERE estado = 'reembolsado'")
    op.execute("DROP INDEX IF EXISTS ix_pago_sena_aprobacion_reembolsado_por")
    for columna in ("reembolso_referencia", "reembolsado_por_usuario_id", "reembolsado_en"):
        op.execute(f"ALTER TABLE pago_sena_aprobacion DROP COLUMN {columna}")
    op.execute("ALTER TABLE pago_sena_aprobacion ADD CONSTRAINT pago_sena_aprobacion_estado_check "
               "CHECK (estado IN ('aplicado', 'en_revision', 'a_reembolsar'))")

    op.execute("ALTER TABLE pago_sena DROP CONSTRAINT ck_pago_sena_reembolso")
    op.execute("ALTER TABLE pago_sena DROP CONSTRAINT ck_pago_sena_reembolso_ref_len")
    op.execute("ALTER TABLE pago_sena DROP CONSTRAINT pago_sena_estado_check")
    op.execute("UPDATE pago_sena SET estado = 'a_reembolsar' WHERE estado = 'reembolsado'")
    for indice in ("ix_pago_sena_por_resolver", "ix_pago_sena_reembolsado_en", "ix_pago_sena_acreditado_en",
                   "ix_pago_sena_reembolsado_por"):
        op.execute(f"DROP INDEX IF EXISTS {indice}")
    for columna in ("reembolso_referencia", "reembolsado_por_usuario_id", "reembolsado_en"):
        op.execute(f"ALTER TABLE pago_sena DROP COLUMN {columna}")
    op.execute(f"ALTER TABLE pago_sena ADD CONSTRAINT pago_sena_estado_check CHECK (estado IN ({ESTADOS_ANTERIORES}))")

    op.execute("DROP EXTENSION IF EXISTS unaccent")
