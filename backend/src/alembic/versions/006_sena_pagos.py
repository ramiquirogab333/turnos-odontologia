"""006: seña y pagos del turno (C-06; R4, R5, R6, R14).

- ``turno.en_espera_vence_en`` (TIMESTAMPTZ) + CHECK: un ``en_espera`` siempre tiene vencimiento.
- ``configuracion_sena`` (singleton, id = 1): porcentaje, medios, textos y plazos editables por el admin.
- ``pago_sena``: estado ``en_revision`` (monto/moneda informados no coinciden, RN-SN-09); un pago activo por turno (``uq_pago_sena_activo``), dinero en ``NUMERIC(10,2)``.

Los EXCLUDE de la 001 no se tocan: ``en_espera`` no bloquea agenda (R8) y el
``UPDATE en_espera -> reservado`` sigue protegido por la base (R5).

Reversible (R14). El ``downgrade`` es destructivo para ``pago_sena``: cancela antes los
``en_espera`` (quedarían sin vencimiento) y borra el historial de señas.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "006_sena_pagos"
down_revision: Union[str, None] = "005_reserva_publica"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

POLITICA_REEMBOLSO = (
    "Si cancelás con 24 h o más de anticipación, te devolvemos la seña. "
    "Si no asistís, la seña no se devuelve."
)


def upgrade() -> None:
    op.execute("ALTER TABLE turno ADD COLUMN en_espera_vence_en TIMESTAMPTZ NULL")
    op.execute(
        "ALTER TABLE turno ADD CONSTRAINT ck_turno_en_espera_vence "
        "CHECK (estado <> 'en_espera' OR en_espera_vence_en IS NOT NULL)"
    )
    op.execute(
        "CREATE INDEX ix_turno_en_espera_vence ON turno (en_espera_vence_en) "
        "WHERE estado = 'en_espera'"
    )

    op.execute(
        """
        CREATE TABLE configuracion_sena (
          id                               SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
          sena_porcentaje                  NUMERIC(5, 2) NOT NULL
            CHECK (sena_porcentaje > 0 AND sena_porcentaje <= 100),
          medios_habilitados               TEXT[] NOT NULL
            CHECK (cardinality(medios_habilitados) >= 1
                   AND medios_habilitados <@ ARRAY['mercadopago', 'transferencia']),
          texto_politica_reembolso         TEXT NOT NULL
            CHECK (LENGTH(texto_politica_reembolso) BETWEEN 1 AND 500),
          expiracion_mp_minutos            INTEGER NOT NULL
            CHECK (expiracion_mp_minutos BETWEEN 5 AND 1440),
          expiracion_transferencia_minutos INTEGER NOT NULL
            CHECK (expiracion_transferencia_minutos BETWEEN 5 AND 4320),
          transferencia_alias              TEXT NULL
            CHECK (transferencia_alias IS NULL OR LENGTH(transferencia_alias) BETWEEN 6 AND 40),
          transferencia_cbu                TEXT NULL
            CHECK (transferencia_cbu IS NULL OR transferencia_cbu ~ '^[0-9]{22}$'),
          transferencia_titular            TEXT NULL
            CHECK (transferencia_titular IS NULL OR LENGTH(transferencia_titular) BETWEEN 1 AND 120),
          created_at                       TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at                       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "INSERT INTO configuracion_sena (id, sena_porcentaje, medios_habilitados, texto_politica_reembolso, "
        "expiracion_mp_minutos, expiracion_transferencia_minutos) "
        f"VALUES (1, 30.00, '{{mercadopago,transferencia}}', '{POLITICA_REEMBOLSO}', 30, 1440)"
    )

    op.execute(
        """
        CREATE TABLE pago_sena (
          id                        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          turno_id                  BIGINT NOT NULL REFERENCES turno (id) ON DELETE RESTRICT,
          medio                     TEXT NOT NULL CHECK (medio IN ('mercadopago', 'transferencia')),
          monto                     NUMERIC(10, 2) NOT NULL CHECK (monto > 0),
          porcentaje_aplicado       NUMERIC(5, 2) NOT NULL
            CHECK (porcentaje_aplicado > 0 AND porcentaje_aplicado <= 100),
          estado                    TEXT NOT NULL DEFAULT 'pendiente'
            CHECK (estado IN ('pendiente', 'acreditado', 'vencido', 'no_reembolsado', 'a_reembolsar',
                              'en_revision')),
          referencia_externa        TEXT NOT NULL CHECK (LENGTH(referencia_externa) BETWEEN 8 AND 64),
          mp_payment_id             TEXT NULL CHECK (mp_payment_id IS NULL OR LENGTH(mp_payment_id) <= 64),
          checkout_url              TEXT NULL CHECK (checkout_url IS NULL OR LENGTH(checkout_url) <= 2048),
          vence_en                  TIMESTAMPTZ NOT NULL,
          monto_reportado           NUMERIC(10, 2) NULL CHECK (monto_reportado IS NULL OR monto_reportado >= 0),
          moneda_reportada          TEXT NULL CHECK (moneda_reportada IS NULL OR LENGTH(moneda_reportada) <= 8),
          acreditado_en             TIMESTAMPTZ NULL,
          acreditado_por_usuario_id BIGINT NULL REFERENCES usuario (id) ON DELETE RESTRICT,
          created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
          CONSTRAINT uq_pago_sena_referencia UNIQUE (referencia_externa),
          CONSTRAINT uq_pago_sena_mp_payment UNIQUE (mp_payment_id),
          CONSTRAINT ck_pago_sena_acreditado
            CHECK (estado NOT IN ('acreditado', 'no_reembolsado') OR acreditado_en IS NOT NULL)
        )
        """
    )
    op.execute("CREATE INDEX ix_pago_sena_turno ON pago_sena (turno_id)")
    op.execute("CREATE INDEX ix_pago_sena_acreditado_por ON pago_sena (acreditado_por_usuario_id)")
    op.execute(
        "CREATE UNIQUE INDEX uq_pago_sena_activo ON pago_sena (turno_id) "
        "WHERE estado IN ('pendiente', 'acreditado')"
    )
    op.execute(
        "CREATE INDEX ix_pago_sena_pendiente_vence ON pago_sena (vence_en) WHERE estado = 'pendiente'"
    )
    # RN-SN-10: cada pago aprobado de la pasarela se registra por su id; los sobrantes y los pagos en
    # revisión conservan trazabilidad para la devolución manual.
    op.execute(
        """
        CREATE TABLE pago_sena_aprobacion (
          id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          pago_id          BIGINT NOT NULL REFERENCES pago_sena (id) ON DELETE RESTRICT,
          mp_payment_id    TEXT NOT NULL CHECK (LENGTH(mp_payment_id) BETWEEN 1 AND 128),
          estado           TEXT NOT NULL CHECK (estado IN ('aplicado', 'en_revision', 'a_reembolsar')),
          monto_reportado  NUMERIC(10, 2) NULL CHECK (monto_reportado IS NULL OR monto_reportado >= 0),
          moneda_reportada TEXT NULL CHECK (moneda_reportada IS NULL OR LENGTH(moneda_reportada) <= 8),
          created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
          CONSTRAINT uq_pago_sena_aprobacion_mp UNIQUE (mp_payment_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_pago_sena_aprobacion_pago ON pago_sena_aprobacion (pago_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_pago_sena_aprobacion_pago")
    op.execute("DROP TABLE IF EXISTS pago_sena_aprobacion")
    op.execute("DROP INDEX IF EXISTS ix_pago_sena_pendiente_vence")
    op.execute("DROP INDEX IF EXISTS uq_pago_sena_activo")
    op.execute("DROP INDEX IF EXISTS ix_pago_sena_acreditado_por")
    op.execute("DROP INDEX IF EXISTS ix_pago_sena_turno")
    op.execute("DROP TABLE IF EXISTS pago_sena")
    op.execute("DROP TABLE IF EXISTS configuracion_sena")
    # Sin vencimiento un en_espera quedaría fuera de contrato: se cancelan antes de quitar la columna.
    op.execute("UPDATE turno SET estado = 'cancelado' WHERE estado = 'en_espera'")
    op.execute("DROP INDEX IF EXISTS ix_turno_en_espera_vence")
    op.execute("ALTER TABLE turno DROP CONSTRAINT IF EXISTS ck_turno_en_espera_vence")
    op.execute("ALTER TABLE turno DROP COLUMN IF EXISTS en_espera_vence_en")
