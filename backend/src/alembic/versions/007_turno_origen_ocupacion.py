"""007: ``turno.origen`` y ocupación de agenda con ``atendido`` (C-08; R4, R5, R14).

- ``turno.origen`` (TEXT NOT NULL DEFAULT 'web', CHECK web/manual/whatsapp). Backfill: los turnos
  sin ``codigo_gestion`` son altas internas -> ``manual``.
- O19 / D11: un turno ``atendido`` ocupa la agenda hasta su ``fin``. Se recrean, con el MISMO nombre
  (``motivo_desde_mensaje`` los usa para elegir el motivo del 409), los dos EXCLUDE de la 001 con el
  predicado ``estado IN ('reservado', 'confirmado', 'atendido')``. Antes se buscan pares que pasarían
  a solaparse: si hay alguno la migración ABORTA listando los ids, sin modificar datos (corregirlos es
  una decisión humana).

Reversible (R14): el ``downgrade`` vuelve al predicado de la 001, que es más chico y nunca falla.
Costo: recrear los EXCLUDE reconstruye el índice GiST con lock exclusivo sobre ``turno``.

Revision ID: 007_turno_origen_ocupacion
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007_turno_origen_ocupacion"
down_revision: Union[str, None] = "006_sena_pagos"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PREDICADO_NUEVO = "estado IN ('reservado', 'confirmado', 'atendido')"
PREDICADO_001 = "estado IN ('reservado', 'confirmado')"

# Pares (a.id < b.id) que hoy conviven y con el predicado nuevo violarían un EXCLUDE: ambos ocupan agenda
# con el predicado nuevo, comparten profesional o sillón, se pisan en el tiempo y al menos uno es atendido.
SQL_CONFLICTOS = """
    SELECT a.id AS id_a, b.id AS id_b
    FROM turno a
    JOIN turno b ON a.id < b.id AND a.periodo && b.periodo
      AND (a.profesional_id = b.profesional_id OR a.sillon_id = b.sillon_id)
    WHERE a.estado IN ('reservado', 'confirmado', 'atendido')
      AND b.estado IN ('reservado', 'confirmado', 'atendido')
      AND (a.estado = 'atendido' OR b.estado = 'atendido')
    ORDER BY a.id, b.id
"""


def _recrear_exclude(predicado: str) -> None:
    for nombre, columna in (("turno_no_solape_profesional", "profesional_id"), ("turno_no_solape_sillon", "sillon_id")):
        op.execute(f"ALTER TABLE turno DROP CONSTRAINT IF EXISTS {nombre}")
        op.execute(
            f"ALTER TABLE turno ADD CONSTRAINT {nombre} "
            f"EXCLUDE USING gist ({columna} WITH =, periodo WITH &&) WHERE ({predicado})"
        )


def upgrade() -> None:
    op.execute("ALTER TABLE turno ADD COLUMN origen TEXT NOT NULL DEFAULT 'web'")
    op.execute(
        "ALTER TABLE turno ADD CONSTRAINT ck_turno_origen "
        "CHECK (origen IN ('web', 'manual', 'whatsapp'))"
    )
    op.execute("UPDATE turno SET origen = 'manual' WHERE codigo_gestion IS NULL")

    conflictos = op.get_bind().execute(sa.text(SQL_CONFLICTOS)).all()
    if conflictos:
        ids = sorted({int(i) for fila in conflictos for i in (fila.id_a, fila.id_b)})
        pares = ", ".join(f"({fila.id_a}, {fila.id_b})" for fila in conflictos)
        raise RuntimeError(
            "007 abortada sin modificar datos: hay turnos superpuestos con un turno atendido "
            f"(ids: {', '.join(str(i) for i in ids)}; pares: {pares}). Corregilos (cancelar o mover) y reintentá."
        )
    _recrear_exclude(PREDICADO_NUEVO)


def downgrade() -> None:
    _recrear_exclude(PREDICADO_001)
    op.execute("ALTER TABLE turno DROP CONSTRAINT IF EXISTS ck_turno_origen")
    op.execute("ALTER TABLE turno DROP COLUMN IF EXISTS origen")
