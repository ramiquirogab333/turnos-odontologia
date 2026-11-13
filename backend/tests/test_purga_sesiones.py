"""C-15 (9.1): purga de sesiones vencidas sin reabrir ninguna cerrada. PostgreSQL real, reloj inyectado. Datos sintéticos (R19)."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.auth.sesiones import purgar_sesiones
from app.models.auth import SesionPanel
from tests.conftest import crear_sesion_sintetica, crear_usuario_panel

AHORA = datetime(2031, 6, 2, 12, 0, tzinfo=timezone.utc)
MARGEN = timedelta(hours=1)


async def _sesion(factory, uid: int, *, vence: datetime, revocada: bool = False) -> str:
    async with factory() as s:
        fila = SesionPanel(sid=uuid4(), usuario_id=uid, refresh_jti=uuid4(), creada_en=vence - timedelta(hours=12),
                           expira_en=vence, revocada_en=AHORA - timedelta(minutes=10) if revocada else None,
                           motivo_revocacion="logout" if revocada else None)
        s.add(fila)
        await s.commit()
        return str(fila.sid)


async def _sids(factory) -> set[str]:
    async with factory() as s:
        return {str(x) for x in (await s.execute(select(SesionPanel.sid))).scalars()}


async def _purgar(factory, *, lote: int = 500) -> int:
    async with factory() as s:
        return await purgar_sesiones(s, AHORA, MARGEN, lote)


async def test_se_borra_la_vencida_hace_dos_horas_y_quedan_las_vigentes(session_factory) -> None:
    uid, _ = await crear_usuario_panel(session_factory, "recepcion@turnos.test", ["recepcion"])
    vieja = await _sesion(session_factory, uid, vence=AHORA - timedelta(hours=2))
    vigente = await _sesion(session_factory, uid, vence=AHORA + timedelta(hours=3))
    assert await _purgar(session_factory) == 1
    restantes = await _sids(session_factory)
    assert vieja not in restantes and vigente in restantes


async def test_una_sesion_revocada_y_no_vencida_se_conserva_y_su_refresh_sigue_siendo_401(session_factory) -> None:
    from app.main import app

    uid, _ = await crear_usuario_panel(session_factory, "recepcion@turnos.test", ["recepcion"])
    ahora_real = datetime.now(timezone.utc)
    sid, _, refresh = await crear_sesion_sintetica(session_factory, uid, "recepcion@turnos.test", ["recepcion"],
                                                   creada_en=ahora_real, expira_en=ahora_real + timedelta(hours=5))
    async with session_factory() as s:
        fila = (await s.execute(select(SesionPanel).where(SesionPanel.sid == __import__("uuid").UUID(sid)))).scalar_one()
        fila.revocada_en, fila.motivo_revocacion = ahora_real - timedelta(minutes=10), "logout"
        await s.commit()
    async with session_factory() as s:
        assert await purgar_sesiones(s, ahora_real, MARGEN, 500) == 0
    assert sid in await _sids(session_factory)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as https:
        https.cookies.set("refresh_token", refresh, domain="test", path="/api/auth")
        assert (await https.post("/api/auth/refresh", headers={"X-Panel-Csrf": "1"})).status_code == 401


async def test_dentro_del_margen_se_conserva_y_en_un_ciclo_posterior_se_borra(session_factory) -> None:
    uid, _ = await crear_usuario_panel(session_factory, "recepcion@turnos.test", ["recepcion"])
    sid = await _sesion(session_factory, uid, vence=AHORA - timedelta(minutes=30))
    assert await _purgar(session_factory) == 0 and sid in await _sids(session_factory)
    async with session_factory() as s:
        assert await purgar_sesiones(s, AHORA + timedelta(minutes=31), MARGEN, 500) == 1
    assert sid not in await _sids(session_factory)


async def test_justo_en_el_limite_del_margen_se_conserva(session_factory) -> None:
    uid, _ = await crear_usuario_panel(session_factory, "recepcion@turnos.test", ["recepcion"])
    await _sesion(session_factory, uid, vence=AHORA - MARGEN)  # expira_en == ahora - margen: no es estrictamente menor
    assert await _purgar(session_factory) == 0


async def test_mil_quinientas_vencidas_con_dos_purgas_en_paralelo_y_lotes_de_500(session_factory) -> None:
    uid, _ = await crear_usuario_panel(session_factory, "recepcion@turnos.test", ["recepcion"])
    async with session_factory() as s:
        s.add_all([SesionPanel(sid=uuid4(), usuario_id=uid, refresh_jti=uuid4(),
                               creada_en=AHORA - timedelta(hours=20), expira_en=AHORA - timedelta(hours=2, seconds=i))
                   for i in range(1500)])
        s.add_all([SesionPanel(sid=uuid4(), usuario_id=uid, refresh_jti=uuid4(), creada_en=AHORA,
                               expira_en=AHORA + timedelta(hours=1, seconds=i)) for i in range(3)])
        await s.commit()
    resultados = await asyncio.gather(_purgar(session_factory, lote=500), _purgar(session_factory, lote=500))
    assert sum(resultados) == 1500
    async with session_factory() as s:
        quedan = (await s.execute(select(func.count()).select_from(SesionPanel))).scalar_one()
        vencidas = (await s.execute(select(func.count()).select_from(SesionPanel)
                                    .where(SesionPanel.expira_en < AHORA - MARGEN))).scalar_one()
    assert vencidas == 0 and quedan == 4  # 3 vigentes + la sesión del usuario de prueba creada por el helper


async def test_el_log_solo_dice_la_cantidad(session_factory, caplog: pytest.LogCaptureFixture) -> None:
    from app.jobs.registro import trabajos_programados
    from app.shared.settings import get_settings

    uid, _ = await crear_usuario_panel(session_factory, "recepcion@turnos.test", ["recepcion"])
    sid = await _sesion(session_factory, uid, vence=AHORA - timedelta(hours=5))
    trabajo = next(t for t in trabajos_programados(get_settings()) if t.nombre == "purga_sesiones")
    caplog.set_level(logging.INFO)
    async with session_factory() as s:
        borradas = await trabajo.funcion(s, AHORA)
    assert borradas == 1
    texto = " ".join(r.getMessage() for r in caplog.records)
    assert "1" in texto and sid not in texto and "recepcion@turnos.test" not in texto


async def test_un_token_de_una_sesion_ya_purgada_es_401_nunca_200_ni_500(session_factory, reloj) -> None:
    from app.main import app

    uid, _ = await crear_usuario_panel(session_factory, "recepcion@turnos.test", ["recepcion"])
    ahora_real = datetime.now(timezone.utc)
    _, access, refresh = await crear_sesion_sintetica(session_factory, uid, "recepcion@turnos.test", ["recepcion"],
                                                      creada_en=ahora_real, expira_en=ahora_real + timedelta(hours=1))
    adelantado = ahora_real + timedelta(hours=3)  # reloj de la máquina adelantado: venció hace 2 h, margen de 1 h
    async with session_factory() as s:
        assert await purgar_sesiones(s, adelantado, MARGEN, 500) == 1
    reloj(adelantado)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as https:
        assert (await https.get("/api/auth/me", headers={"Authorization": f"Bearer {access}"})).status_code == 401
        https.cookies.set("refresh_token", refresh, domain="test", path="/api/auth")
        assert (await https.post("/api/auth/refresh", headers={"X-Panel-Csrf": "1"})).status_code == 401
