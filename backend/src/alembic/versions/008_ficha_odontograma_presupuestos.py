"""008: ficha clínica, odontograma, presupuestos y pagos de presupuesto (C-11; R4, R5, R6, R14).

Cinco tablas nuevas, sin cambios a las existentes. Dinero en ``NUMERIC``, fechas en ``TIMESTAMPTZ``, textos con
``CHECK`` de longitud, toda FK con su índice y las invariantes de dominio repetidas como ``CHECK`` (defensa en
profundidad). ``downgrade`` borra en orden inverso (reversible, R14).

Revision ID: 008_ficha_odonto_presup (id acortado: alembic_version.version_num es VARCHAR(32))
"""

from typing import Sequence, Union

from alembic import op

revision: str = "008_ficha_odonto_presup"
down_revision: Union[str, None] = "007_turno_origen_ocupacion"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PIEZA_FDI = (
    "(pieza BETWEEN 11 AND 18 OR pieza BETWEEN 21 AND 28 OR pieza BETWEEN 31 AND 38 OR pieza BETWEEN 41 AND 48 "
    "OR pieza BETWEEN 51 AND 55 OR pieza BETWEEN 61 AND 65 OR pieza BETWEEN 71 AND 75 OR pieza BETWEEN 81 AND 85)"
)


def upgrade() -> None:
    op.execute(f"""
        CREATE TABLE ficha (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            paciente_id BIGINT NOT NULL UNIQUE REFERENCES paciente (id) ON DELETE RESTRICT,
            alergias TEXT NOT NULL DEFAULT '',
            medicacion TEXT NOT NULL DEFAULT '',
            antecedentes_medicos TEXT NOT NULL DEFAULT '',
            observaciones TEXT NOT NULL DEFAULT '',
            version INTEGER NOT NULL DEFAULT 1,
            actualizado_por BIGINT REFERENCES usuario (id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_ficha_alergias_len CHECK (LENGTH(alergias) <= 2000),
            CONSTRAINT ck_ficha_medicacion_len CHECK (LENGTH(medicacion) <= 2000),
            CONSTRAINT ck_ficha_antecedentes_len CHECK (LENGTH(antecedentes_medicos) <= 2000),
            CONSTRAINT ck_ficha_observaciones_len CHECK (LENGTH(observaciones) <= 2000),
            CONSTRAINT ck_ficha_version CHECK (version >= 1)
        )
    """)
    op.execute("CREATE INDEX ix_ficha_actualizado_por ON ficha (actualizado_por)")

    op.execute(f"""
        CREATE TABLE odontograma_registro (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            paciente_id BIGINT NOT NULL REFERENCES paciente (id) ON DELETE RESTRICT,
            pieza SMALLINT NOT NULL,
            cara TEXT,
            estado TEXT NOT NULL,
            nota TEXT,
            registrado_por BIGINT REFERENCES usuario (id) ON DELETE SET NULL,
            registrado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_odontograma_pieza CHECK {PIEZA_FDI},
            CONSTRAINT ck_odontograma_cara CHECK (cara IS NULL OR cara IN ('O', 'M', 'D', 'V', 'L')),
            CONSTRAINT ck_odontograma_estado CHECK (estado IN
                ('sano', 'caries', 'obturado', 'ausente', 'extraccion_indicada', 'corona', 'endodoncia', 'implante')),
            CONSTRAINT ck_odontograma_cara_estado CHECK (
                estado = 'sano'
                OR (estado IN ('caries', 'obturado') AND cara IS NOT NULL)
                OR (estado IN ('ausente', 'extraccion_indicada', 'corona', 'endodoncia', 'implante')
                    AND cara IS NULL)),
            CONSTRAINT ck_odontograma_nota_len CHECK (nota IS NULL OR LENGTH(nota) <= 500)
        )
    """)
    op.execute("CREATE INDEX ix_odontograma_paciente_historial "
               "ON odontograma_registro (paciente_id, registrado_en DESC, id DESC)")
    op.execute("CREATE INDEX ix_odontograma_registrado_por ON odontograma_registro (registrado_por)")

    op.execute("""
        CREATE TABLE presupuesto (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            paciente_id BIGINT NOT NULL REFERENCES paciente (id) ON DELETE RESTRICT,
            obra_social_id BIGINT REFERENCES obra_social (id) ON DELETE RESTRICT,
            estado TEXT NOT NULL DEFAULT 'borrador',
            subtotal NUMERIC(12, 2) NOT NULL DEFAULT 0,
            cobertura_total NUMERIC(12, 2) NOT NULL DEFAULT 0,
            diferencial_total NUMERIC(12, 2) NOT NULL DEFAULT 0,
            total_paciente NUMERIC(12, 2) NOT NULL DEFAULT 0,
            notas TEXT NOT NULL DEFAULT '',
            creado_por BIGINT REFERENCES usuario (id) ON DELETE SET NULL,
            presentado_en TIMESTAMPTZ,
            resuelto_en TIMESTAMPTZ,
            anulado_en TIMESTAMPTZ,
            anulado_motivo TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_presupuesto_estado CHECK (estado IN
                ('borrador', 'presentado', 'aceptado', 'rechazado', 'anulado')),
            CONSTRAINT ck_presupuesto_montos CHECK (
                subtotal >= 0 AND cobertura_total >= 0 AND diferencial_total >= 0 AND total_paciente >= 0),
            CONSTRAINT ck_presupuesto_total CHECK (total_paciente = subtotal - cobertura_total + diferencial_total),
            CONSTRAINT ck_presupuesto_notas_len CHECK (LENGTH(notas) <= 1000),
            CONSTRAINT ck_presupuesto_anulado_motivo_len CHECK (
                anulado_motivo IS NULL OR LENGTH(anulado_motivo) BETWEEN 3 AND 300),
            CONSTRAINT ck_presupuesto_estado_fechas CHECK (
                (estado = 'borrador' AND presentado_en IS NULL AND resuelto_en IS NULL AND anulado_en IS NULL)
                OR (estado = 'presentado' AND presentado_en IS NOT NULL AND resuelto_en IS NULL
                    AND anulado_en IS NULL)
                OR (estado IN ('aceptado', 'rechazado') AND presentado_en IS NOT NULL AND resuelto_en IS NOT NULL
                    AND anulado_en IS NULL)
                OR (estado = 'anulado' AND anulado_en IS NOT NULL AND anulado_motivo IS NOT NULL))
        )
    """)
    op.execute("CREATE INDEX ix_presupuesto_paciente ON presupuesto (paciente_id, created_at DESC)")
    op.execute("CREATE INDEX ix_presupuesto_obra_social ON presupuesto (obra_social_id)")
    op.execute("CREATE INDEX ix_presupuesto_creado_por ON presupuesto (creado_por)")

    op.execute(f"""
        CREATE TABLE presupuesto_linea (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            presupuesto_id BIGINT NOT NULL REFERENCES presupuesto (id) ON DELETE CASCADE,
            orden SMALLINT NOT NULL,
            tratamiento_id BIGINT NOT NULL REFERENCES tratamiento (id) ON DELETE RESTRICT,
            nomenclador_id BIGINT REFERENCES nomenclador (id) ON DELETE SET NULL,
            codigo_prestacion TEXT,
            pieza SMALLINT,
            cara TEXT,
            cantidad SMALLINT NOT NULL,
            precio_unitario NUMERIC(10, 2) NOT NULL,
            cobertura_porcentaje NUMERIC(5, 2) NOT NULL DEFAULT 0,
            arancel_diferencial NUMERIC(10, 2) NOT NULL DEFAULT 0,
            importe_bruto NUMERIC(12, 2) NOT NULL,
            importe_cobertura NUMERIC(12, 2) NOT NULL,
            importe_diferencial NUMERIC(12, 2) NOT NULL,
            importe_paciente NUMERIC(12, 2) NOT NULL,
            CONSTRAINT uq_presupuesto_linea_orden UNIQUE (presupuesto_id, orden),
            CONSTRAINT ck_linea_orden CHECK (orden >= 1),
            CONSTRAINT ck_linea_cantidad CHECK (cantidad BETWEEN 1 AND 99),
            CONSTRAINT ck_linea_pieza CHECK (pieza IS NULL OR {PIEZA_FDI}),
            CONSTRAINT ck_linea_cara CHECK (cara IS NULL OR (pieza IS NOT NULL AND cara IN ('O', 'M', 'D', 'V', 'L'))),
            CONSTRAINT ck_linea_codigo_len CHECK (codigo_prestacion IS NULL OR LENGTH(codigo_prestacion) <= 60),
            CONSTRAINT ck_linea_montos CHECK (
                precio_unitario >= 0 AND importe_bruto >= 0 AND importe_cobertura >= 0
                AND importe_diferencial >= 0 AND importe_paciente >= 0 AND arancel_diferencial >= 0),
            CONSTRAINT ck_linea_cobertura_pct CHECK (cobertura_porcentaje BETWEEN 0 AND 100),
            CONSTRAINT ck_linea_cobertura_tope CHECK (importe_cobertura <= importe_bruto),
            CONSTRAINT ck_linea_importe_paciente CHECK (
                importe_paciente = importe_bruto - importe_cobertura + importe_diferencial)
        )
    """)
    op.execute("CREATE INDEX ix_linea_tratamiento ON presupuesto_linea (tratamiento_id)")
    op.execute("CREATE INDEX ix_linea_nomenclador ON presupuesto_linea (nomenclador_id)")

    op.execute("""
        CREATE TABLE pago_presupuesto (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            presupuesto_id BIGINT NOT NULL REFERENCES presupuesto (id) ON DELETE RESTRICT,
            medio TEXT NOT NULL,
            monto NUMERIC(12, 2) NOT NULL,
            estado TEXT NOT NULL DEFAULT 'registrado',
            fecha_cobro TIMESTAMPTZ NOT NULL,
            referencia TEXT,
            registrado_por BIGINT REFERENCES usuario (id) ON DELETE SET NULL,
            anulado_por BIGINT REFERENCES usuario (id) ON DELETE SET NULL,
            anulado_en TIMESTAMPTZ,
            anulado_motivo TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_pago_presupuesto_medio CHECK (medio IN ('mercadopago', 'transferencia')),
            CONSTRAINT ck_pago_presupuesto_monto CHECK (monto > 0),
            CONSTRAINT ck_pago_presupuesto_estado CHECK (estado IN ('registrado', 'anulado')),
            CONSTRAINT ck_pago_presupuesto_referencia_len CHECK (
                referencia IS NULL OR LENGTH(referencia) BETWEEN 1 AND 64),
            CONSTRAINT ck_pago_presupuesto_anulacion CHECK (
                (estado = 'registrado' AND anulado_en IS NULL AND anulado_motivo IS NULL AND anulado_por IS NULL)
                OR (estado = 'anulado' AND anulado_en IS NOT NULL AND anulado_motivo IS NOT NULL
                    AND LENGTH(anulado_motivo) BETWEEN 3 AND 300))
        )
    """)
    op.execute("CREATE INDEX ix_pago_presupuesto_presupuesto ON pago_presupuesto (presupuesto_id)")
    op.execute("CREATE INDEX ix_pago_presupuesto_registrado_por ON pago_presupuesto (registrado_por)")
    op.execute("CREATE INDEX ix_pago_presupuesto_anulado_por ON pago_presupuesto (anulado_por)")
    op.execute("CREATE INDEX ix_pago_presupuesto_fecha_cobro ON pago_presupuesto (fecha_cobro)")
    op.execute("CREATE UNIQUE INDEX uq_pago_presupuesto_medio_referencia ON pago_presupuesto (medio, referencia) "
               "WHERE referencia IS NOT NULL AND estado = 'registrado'")


def downgrade() -> None:
    for tabla in ("pago_presupuesto", "presupuesto_linea", "presupuesto", "odontograma_registro", "ficha"):
        op.execute(f"DROP TABLE IF EXISTS {tabla}")
