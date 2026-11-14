"""014: baja lógica del catálogo y restricciones de integridad en la base (C-14; D3, D5, D6; O1, O6, O13; R4, R5, R6, R14).

- ``tratamiento.is_active`` y ``profesional.is_active`` (``BOOLEAN NOT NULL DEFAULT true``): las filas previas quedan activas.
  ``disponibilidad`` ya tiene ``is_active`` desde C-02 y ``sillon`` conserva su ``estado``.
- Franjas activas sin superposición: ``EXCLUDE USING gist (profesional_id WITH =, dia_semana WITH =,
  rango_hora(hora_inicio, hora_fin, '[)') WITH &&) WHERE (is_active)``. El rango es semiabierto: 09-13 y 13-17 conviven.
  ``rango_hora`` es un tipo de rango sobre ``time`` (no hay uno nativo); ``btree_gist`` ya está instalado desde la 001.
- Índices únicos sobre ``lower(btrim(...))``: nombre de tratamiento, nombre de sillón y matrícula de profesional.
- Verificaciones previas de solo lectura: si hay datos que violarían una restricción la migración se detiene con un
  ``RuntimeError`` que nombra los ids y no corrige nada solo (la base queda en ``013``: el DDL de Postgres es transaccional).
- ``downgrade`` quita índices, restricción, tipo y columnas en orden inverso, sin perder filas.

Revision ID: 014_catalogo_baja_logica
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014_catalogo_baja_logica"
down_revision: Union[str, None] = "013_auditoria_exportacion"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EXCLUDE_FRANJAS = "ex_disponibilidad_franja_activa"

_FRANJAS_SUPERPUESTAS = """
    SELECT a.id, b.id, a.profesional_id, a.dia_semana, a.hora_inicio, a.hora_fin, b.hora_inicio, b.hora_fin
    FROM disponibilidad a
    JOIN disponibilidad b ON a.id < b.id AND a.profesional_id = b.profesional_id AND a.dia_semana = b.dia_semana
    WHERE a.is_active AND b.is_active AND a.hora_inicio < b.hora_fin AND b.hora_inicio < a.hora_fin
    ORDER BY a.id, b.id
"""

# (tabla, expresión normalizada, descripción para el mensaje)
_UNICOS = (
    ("tratamiento", "nombre", "nombres de tratamiento"),
    ("sillon", "nombre", "nombres de sillón"),
    ("profesional", "matricula", "matrículas de profesional"),
)


def _verificar_datos_existentes() -> None:
    """Aborta con los ids en conflicto si los datos actuales violarían alguna restricción nueva."""
    bind = op.get_bind()
    problemas: list[str] = []
    for a, b, profesional, dia, ini_a, fin_a, ini_b, fin_b in bind.execute(sa.text(_FRANJAS_SUPERPUESTAS)).all():
        problemas.append(
            f"franjas activas superpuestas ids {a} y {b} (profesional {profesional}, día {dia}: "
            f"{ini_a}-{fin_a} y {ini_b}-{fin_b})")
    for tabla, columna, descripcion in _UNICOS:
        filas = bind.execute(sa.text(
            f"SELECT lower(btrim({columna})) AS clave, array_agg(id ORDER BY id) AS ids FROM {tabla} "
            f"GROUP BY 1 HAVING count(*) > 1 ORDER BY 1")).all()
        for clave, ids in filas:
            problemas.append(f"{descripcion} repetidos ids {', '.join(str(i) for i in ids)} ('{clave}')")
    if problemas:
        raise RuntimeError(
            "La migración 014 no puede aplicarse: hay datos que violan las restricciones nuevas. Corregilos a mano y "
            "reintentá (no se modificó nada). " + "; ".join(problemas))


def upgrade() -> None:
    _verificar_datos_existentes()
    for tabla in ("tratamiento", "profesional"):
        op.add_column(tabla, sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.execute("CREATE TYPE rango_hora AS RANGE (subtype = time)")
    op.execute(
        f"ALTER TABLE disponibilidad ADD CONSTRAINT {EXCLUDE_FRANJAS} EXCLUDE USING gist ("
        "profesional_id WITH =, dia_semana WITH =, (rango_hora(hora_inicio, hora_fin, '[)')) WITH &&) "
        "WHERE (is_active)")
    op.execute("CREATE UNIQUE INDEX ux_tratamiento_nombre ON tratamiento (lower(btrim(nombre)))")
    op.execute("CREATE UNIQUE INDEX ux_sillon_nombre ON sillon (lower(btrim(nombre)))")
    op.execute("CREATE UNIQUE INDEX ux_profesional_matricula ON profesional (lower(btrim(matricula)))")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_profesional_matricula")
    op.execute("DROP INDEX IF EXISTS ux_sillon_nombre")
    op.execute("DROP INDEX IF EXISTS ux_tratamiento_nombre")
    op.execute(f"ALTER TABLE disponibilidad DROP CONSTRAINT IF EXISTS {EXCLUDE_FRANJAS}")
    op.execute("DROP TYPE IF EXISTS rango_hora")
    for tabla in ("profesional", "tratamiento"):
        op.drop_column(tabla, "is_active")
