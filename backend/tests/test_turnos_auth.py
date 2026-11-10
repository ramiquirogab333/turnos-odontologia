"""C-08 (2.1, O3): ``POST /api/turnos`` exige recepción o admin. Datos sintéticos (R19)."""

import pytest
from sqlalchemy import func, select

from app.auth.service import create_refresh_token
from app.turnos.models import Turno
from tests.conftest import bearer, crear_usuario_panel, future_iso


def _cuerpo(ids: dict[str, int]) -> dict[str, object]:
    return {**ids, "inicio": future_iso(180)}


async def _turnos(session_factory) -> int:
    async with session_factory() as s:
        return (await s.execute(select(func.count()).select_from(Turno))).scalar_one()


async def test_sin_token_es_401_y_no_crea_el_turno(client, seed_ids, session_factory) -> None:
    r = await client.post("/api/turnos", json=_cuerpo(seed_ids))
    assert r.status_code == 401
    assert await _turnos(session_factory) == 0


async def test_odontologo_es_403_y_no_crea_el_turno(client, seed_ids, session_factory) -> None:
    _, token = await crear_usuario_panel(session_factory, "odonto@turnos.test", ["odontologo"],
                                         profesional_id=seed_ids["profesional_id"])
    r = await client.post("/api/turnos", json=_cuerpo(seed_ids), headers=bearer(token))
    assert r.status_code == 403
    assert await _turnos(session_factory) == 0


async def test_un_token_de_refresh_como_bearer_es_401(client, seed_ids, session_factory) -> None:
    uid, _ = await crear_usuario_panel(session_factory, "rec@turnos.test", ["recepcion"])
    refresh = create_refresh_token({"sub": str(uid), "roles": ["recepcion"], "email": "rec@turnos.test",
                                    "jti": "jti-refresh-sintetico"})
    r = await client.post("/api/turnos", json=_cuerpo(seed_ids), headers=bearer(refresh))
    assert r.status_code == 401
    assert await _turnos(session_factory) == 0


@pytest.mark.parametrize("rol", ["recepcion", "admin"])
async def test_recepcion_y_admin_crean_el_turno(client, seed_ids, session_factory, rol) -> None:
    _, token = await crear_usuario_panel(session_factory, f"{rol}@turnos.test", [rol])
    r = await client.post("/api/turnos", json=_cuerpo(seed_ids), headers=bearer(token))
    assert r.status_code == 201, r.text
    assert await _turnos(session_factory) == 1
