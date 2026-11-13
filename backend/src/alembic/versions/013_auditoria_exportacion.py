"""013: la auditoría pasa a ser de solo agregado (C-13; D6, O4; R4, R6, R14).

Sobre ``registro_auditoria``: la FK de usuario pasa de ``SET NULL`` a ``RESTRICT`` (borrar un usuario ya no borra su
identidad del rastro; desde C-15 los usuarios se desactivan), la IP queda acotada a 45 caracteres (IPv6 máxima), se agrega
el índice de historia por entidad ``(entidad, entidad_id, created_at DESC)`` y un trigger rechaza ``UPDATE`` y
``DELETE`` (SQLSTATE ``P0001``). ``TRUNCATE`` no dispara triggers de fila: queda como vía de mantenimiento del DBA y de
la limpieza de los tests. ``downgrade`` quita trigger, función, índice y CHECK y restaura ``SET NULL``, sin perder filas.

Revision ID: 013_auditoria_exportacion
"""

from typing import Sequence, Union

from alembic import op

revision: str = "013_auditoria_exportacion"
down_revision: Union[str, None] = "012_sesion_panel"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK = "registro_auditoria_usuario_id_fkey"


def upgrade() -> None:
    op.execute(f"ALTER TABLE registro_auditoria DROP CONSTRAINT {FK}")
    op.execute(f"ALTER TABLE registro_auditoria ADD CONSTRAINT {FK} "
               "FOREIGN KEY (usuario_id) REFERENCES usuario (id) ON DELETE RESTRICT")
    op.execute("ALTER TABLE registro_auditoria ADD CONSTRAINT ck_auditoria_ip_len "
               "CHECK (ip IS NULL OR LENGTH(ip) <= 45)")
    op.execute("CREATE INDEX ix_registro_auditoria_entidad "
               "ON registro_auditoria (entidad, entidad_id, created_at DESC)")
    op.execute("""
        CREATE FUNCTION registro_auditoria_inmutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'registro_auditoria es de solo agregado (C-13)' USING ERRCODE = 'P0001';
        END;
        $$
    """)
    op.execute("CREATE TRIGGER trg_registro_auditoria_inmutable BEFORE UPDATE OR DELETE ON registro_auditoria "
               "FOR EACH ROW EXECUTE FUNCTION registro_auditoria_inmutable()")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_registro_auditoria_inmutable ON registro_auditoria")
    op.execute("DROP FUNCTION IF EXISTS registro_auditoria_inmutable()")
    op.execute("DROP INDEX IF EXISTS ix_registro_auditoria_entidad")
    op.execute("ALTER TABLE registro_auditoria DROP CONSTRAINT IF EXISTS ck_auditoria_ip_len")
    op.execute(f"ALTER TABLE registro_auditoria DROP CONSTRAINT {FK}")
    op.execute(f"ALTER TABLE registro_auditoria ADD CONSTRAINT {FK} "
               "FOREIGN KEY (usuario_id) REFERENCES usuario (id) ON DELETE SET NULL")
