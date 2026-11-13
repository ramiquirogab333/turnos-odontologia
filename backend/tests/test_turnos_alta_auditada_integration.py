"""C-13 (5.3, O10): el alta interna ``POST /api/turnos`` deja su registro ``alta_turno_interna``. Datos sintéticos (R19)."""

import asyncio
from datetime import datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.models.core import RegistroAuditoria
from tests.conftest import bearer, crear_usuario_panel, future_iso


def _cliente(socket: tuple[str, int]) -> AsyncClient:
    from app.main import app

    return AsyncClient(transport=ASGITransport(app=app, client=socket), base_url="https://test")


async def _altas(factory) -> list[RegistroAuditoria]:  # type: ignore[no-untyped-def]
    async with factory() as s:
        return list((await s.execute(select(RegistroAuditoria).where(RegistroAuditoria.accion == "alta_turno_interna")
                                     .order_by(RegistroAuditoria.id))).scalars())


async def test_el_alta_interna_deja_registro_con_usuario_ip_y_ids_sin_datos_personales(
        session_factory, seed_ids) -> None:  # type: ignore[no-untyped-def]
    uid, token = await crear_usuario_panel(session_factory, "recepcion@turnos.test", ["recepcion"])
    async with _cliente(("203.0.113.31", 4000)) as c:
        r = await c.post("/api/turnos", json={**seed_ids, "inicio": future_iso(120)}, headers=bearer(token))
    assert r.status_code == 201, r.text
    [registro] = await _altas(session_factory)
    assert (registro.usuario_id, registro.entidad, registro.entidad_id, registro.ip) == (
        uid, "turno", str(r.json()["id"]), "203.0.113.31")
    d = registro.datos_despues
    assert (d["profesional_id"], d["sillon_id"], d["tratamiento_id"], d["estado"]) == (
        seed_ids["profesional_id"], seed_ids["sillon_id"], seed_ids["tratamiento_id"], "reservado")
    assert datetime.fromisoformat(d["inicio"]) == datetime.fromisoformat(r.json()["inicio"])
    assert datetime.fromisoformat(d["fin"]) == datetime.fromisoformat(r.json()["fin"])
    assert "codigo_gestion" not in d and "contacto_nombre" not in d


async def test_un_alta_con_solape_o_rechazada_no_deja_registro(client_recepcion, seed_ids, session_factory) -> None:  # type: ignore[no-untyped-def]
    inicio = future_iso(120)
    assert (await client_recepcion.post("/api/turnos", json={**seed_ids, "inicio": inicio})).status_code == 201
    assert (await client_recepcion.post("/api/turnos", json={**seed_ids, "inicio": inicio})).status_code == 409
    assert (await client_recepcion.post("/api/turnos", json={**seed_ids, "inicio": future_iso(-30)})
            ).status_code == 422
    assert len(await _altas(session_factory)) == 1  # solo la del 201


async def test_un_rol_sin_permiso_no_deja_registro(client, seed_ids, session_factory) -> None:  # type: ignore[no-untyped-def]
    _, token = await crear_usuario_panel(session_factory, "dra.ficticia@turnos.test", ["odontologo"])
    r = await client.post("/api/turnos", json={**seed_ids, "inicio": future_iso(120)}, headers=bearer(token))
    assert r.status_code == 403
    assert await _altas(session_factory) == []


async def test_dos_altas_simultaneas_por_el_mismo_horario_dan_un_201_un_409_y_un_solo_registro(
        client_recepcion, seed_ids, session_factory) -> None:  # type: ignore[no-untyped-def]
    cuerpo = {**seed_ids, "inicio": future_iso(180)}
    resultados = await asyncio.gather(client_recepcion.post("/api/turnos", json=cuerpo),
                                      client_recepcion.post("/api/turnos", json=cuerpo))
    assert sorted(r.status_code for r in resultados) == [201, 409]
    assert len(await _altas(session_factory)) == 1


async def test_si_falla_guardar_el_registro_el_turno_no_se_crea(
        client_recepcion, seed_ids, session_factory, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    from app.main import app
    from app.turnos import service
    from app.turnos.models import Turno

    def _falla(*args: object, **kwargs: object) -> None:
        raise RuntimeError("auditoría caída (simulada)")

    monkeypatch.setattr(service, "registrar", _falla, raising=False)
    cabecera = dict(client_recepcion.headers)
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False),
                           base_url="http://test") as c:
        r = await c.post("/api/turnos", json={**seed_ids, "inicio": future_iso(120)}, headers=cabecera)
    assert r.status_code == 500
    async with session_factory() as s:
        assert (await s.execute(select(Turno.id))).first() is None
