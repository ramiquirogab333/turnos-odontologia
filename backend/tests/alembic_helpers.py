"""Ayudas de los tests de migración (C-08): corren Alembic como subproceso contra la base de pruebas."""

import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def alembic(*args: str) -> subprocess.CompletedProcess[str]:
    url = os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://turnos:turnos@localhost:5433/turnos")
    entorno = {**os.environ, "DATABASE_URL": url, "PYTHONPATH": str(BACKEND / "src")}
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=entorno,
                          capture_output=True, text=True, timeout=120)
