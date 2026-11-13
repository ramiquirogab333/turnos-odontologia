"""011: sincronización con Google Calendar (C-10; R4, R6, R14).

Tres tablas: ``gcal_conexion`` (una por profesional, tokens OAuth cifrados), ``evento_calendar`` (vínculo
``Turno <-> evento de Google`` y franjas ocupadas ajenas, con un único evento vigente por turno y conexión) y
``gcal_conflicto`` (desacuerdos a resolver a mano, RN-GC-02). Instantes en ``TIMESTAMPTZ``, textos con ``CHECK``, toda
FK con su índice. De un evento ajeno solo se guarda horario y ocupación (Ley 25.326). El índice GiST de las franjas
usa ``btree_gist`` (creada en 001). ``downgrade`` borra las tres tablas: se pierde el vínculo con Google (los eventos
ya creados quedan en los calendarios).

Revision ID: 011_google_calendar
"""

from typing import Sequence, Union

from alembic import op

revision: str = "011_google_calendar"
down_revision: Union[str, None] = "010_recordatorios"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE gcal_conexion (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            profesional_id BIGINT NOT NULL REFERENCES profesional (id) ON DELETE RESTRICT,
            usuario_id BIGINT REFERENCES usuario (id) ON DELETE SET NULL,
            estado TEXT NOT NULL,
            cuenta_email TEXT,
            calendario_id TEXT NOT NULL DEFAULT 'primary',
            refresh_token_cifrado TEXT,
            access_token_cifrado TEXT,
            access_expira_en TIMESTAMPTZ,
            sync_token TEXT,
            oauth_nonce_hash TEXT,
            oauth_verifier_cifrado TEXT,
            oauth_expira_en TIMESTAMPTZ,
            ultimo_sync_ok_en TIMESTAMPTZ,
            proximo_intento_en TIMESTAMPTZ,
            fallos_consecutivos INTEGER NOT NULL DEFAULT 0,
            ultimo_error TEXT,
            conectada_en TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_gcal_conexion_profesional_id UNIQUE (profesional_id),
            CONSTRAINT ck_gcal_conexion_estado CHECK (estado IN ('pendiente', 'activa', 'revocada', 'desconectada')),
            CONSTRAINT ck_gcal_conexion_email_len CHECK (cuenta_email IS NULL OR LENGTH(cuenta_email) <= 254),
            CONSTRAINT ck_gcal_conexion_calendario_len CHECK (LENGTH(calendario_id) BETWEEN 1 AND 255),
            CONSTRAINT ck_gcal_conexion_refresh_len CHECK (
                refresh_token_cifrado IS NULL OR LENGTH(refresh_token_cifrado) <= 4096),
            CONSTRAINT ck_gcal_conexion_access_len CHECK (
                access_token_cifrado IS NULL OR LENGTH(access_token_cifrado) <= 4096),
            CONSTRAINT ck_gcal_conexion_verifier_len CHECK (
                oauth_verifier_cifrado IS NULL OR LENGTH(oauth_verifier_cifrado) <= 4096),
            CONSTRAINT ck_gcal_conexion_sync_token_len CHECK (sync_token IS NULL OR LENGTH(sync_token) <= 2048),
            CONSTRAINT ck_gcal_conexion_fallos CHECK (fallos_consecutivos >= 0),
            CONSTRAINT ck_gcal_conexion_error_len CHECK (ultimo_error IS NULL OR LENGTH(ultimo_error) <= 300),
            CONSTRAINT ck_gcal_conexion_activa_token CHECK (estado <> 'activa' OR refresh_token_cifrado IS NOT NULL),
            CONSTRAINT ck_gcal_conexion_pendiente_state CHECK (
                estado <> 'pendiente' OR (oauth_nonce_hash IS NOT NULL AND oauth_expira_en IS NOT NULL))
        )
    """)
    op.execute("CREATE INDEX ix_gcal_conexion_usuario_id ON gcal_conexion (usuario_id)")
    op.execute("CREATE INDEX ix_gcal_conexion_trabajo ON gcal_conexion (proximo_intento_en) WHERE estado = 'activa'")

    op.execute("""
        CREATE TABLE evento_calendar (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            conexion_id BIGINT NOT NULL REFERENCES gcal_conexion (id) ON DELETE RESTRICT,
            turno_id BIGINT REFERENCES turno (id) ON DELETE RESTRICT,
            origen TEXT NOT NULL,
            google_event_id TEXT NOT NULL,
            estado TEXT NOT NULL,
            inicio TIMESTAMPTZ NOT NULL,
            fin TIMESTAMPTZ NOT NULL,
            ocupa BOOLEAN NOT NULL DEFAULT true,
            etag TEXT,
            hash_contenido TEXT,
            generacion INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_evento_calendar_origen CHECK (origen IN ('sistema', 'google')),
            CONSTRAINT ck_evento_calendar_estado CHECK (
                estado IN ('pendiente', 'sincronizado', 'borrado', 'desvinculado')),
            CONSTRAINT ck_evento_calendar_google_id_len CHECK (LENGTH(google_event_id) BETWEEN 5 AND 1024),
            CONSTRAINT ck_evento_calendar_fin_after_inicio CHECK (fin > inicio),
            CONSTRAINT ck_evento_calendar_etag_len CHECK (etag IS NULL OR LENGTH(etag) <= 255),
            CONSTRAINT ck_evento_calendar_hash_len CHECK (hash_contenido IS NULL OR LENGTH(hash_contenido) <= 64),
            CONSTRAINT ck_evento_calendar_generacion CHECK (generacion >= 0),
            CONSTRAINT ck_evento_calendar_origen_turno CHECK ((origen = 'sistema') = (turno_id IS NOT NULL))
        )
    """)
    # Cubre además el índice de la FK conexion_id (R6).
    op.execute("CREATE UNIQUE INDEX uq_evento_calendar_conexion_google_id ON evento_calendar (conexion_id, google_event_id)")
    op.execute("CREATE INDEX ix_evento_calendar_turno_id ON evento_calendar (turno_id)")
    # Un evento vigente por turno y conexión; el historial (borrado/desvinculado) no cuenta.
    op.execute("CREATE UNIQUE INDEX uq_evento_calendar_vigente ON evento_calendar (conexion_id, turno_id) "
               "WHERE origen = 'sistema' AND estado IN ('pendiente', 'sincronizado')")
    # Disponibilidad: franjas ajenas que ocupan, por conexión y rango.
    op.execute("CREATE INDEX ix_evento_calendar_franjas ON evento_calendar "
               "USING gist (conexion_id, tstzrange(inicio, fin, '[)')) WHERE origen = 'google' AND ocupa")

    op.execute("""
        CREATE TABLE gcal_conflicto (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            conexion_id BIGINT NOT NULL REFERENCES gcal_conexion (id) ON DELETE RESTRICT,
            turno_id BIGINT NOT NULL REFERENCES turno (id) ON DELETE RESTRICT,
            evento_id BIGINT NOT NULL REFERENCES evento_calendar (id) ON DELETE RESTRICT,
            tipo TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'abierto',
            sistema_inicio TIMESTAMPTZ NOT NULL,
            sistema_fin TIMESTAMPTZ NOT NULL,
            google_inicio TIMESTAMPTZ,
            google_fin TIMESTAMPTZ,
            resolucion TEXT,
            resuelto_por_usuario_id BIGINT REFERENCES usuario (id) ON DELETE SET NULL,
            detectado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            resuelto_en TIMESTAMPTZ,
            CONSTRAINT ck_gcal_conflicto_tipo CHECK (
                tipo IN ('movido_en_google', 'borrado_en_google', 'solapa_evento_externo')),
            CONSTRAINT ck_gcal_conflicto_estado CHECK (estado IN ('abierto', 'resuelto')),
            CONSTRAINT ck_gcal_conflicto_resolucion CHECK (resolucion IS NULL OR resolucion IN (
                'restaurar_en_google', 'desvincular', 'revisado', 'turno_cancelado', 'solape_desaparecido')),
            CONSTRAINT ck_gcal_conflicto_resuelto CHECK (
                (estado = 'resuelto') = (resolucion IS NOT NULL) AND (estado = 'resuelto') = (resuelto_en IS NOT NULL))
        )
    """)
    op.execute("CREATE INDEX ix_gcal_conflicto_turno_id ON gcal_conflicto (turno_id)")
    op.execute("CREATE INDEX ix_gcal_conflicto_evento_id ON gcal_conflicto (evento_id)")
    op.execute("CREATE INDEX ix_gcal_conflicto_resuelto_por_usuario_id ON gcal_conflicto (resuelto_por_usuario_id)")
    # Un conflicto abierto por evento, turno y tipo; también indexa evento_id.
    op.execute("CREATE UNIQUE INDEX uq_gcal_conflicto_abierto ON gcal_conflicto (evento_id, turno_id, tipo) "
               "WHERE estado = 'abierto'")
    # Cubre conexion_id (R6) y el listado por estado.
    op.execute("CREATE INDEX ix_gcal_conflicto_listado ON gcal_conflicto (conexion_id, estado)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS gcal_conflicto")
    op.execute("DROP TABLE IF EXISTS evento_calendar")
    op.execute("DROP TABLE IF EXISTS gcal_conexion")
