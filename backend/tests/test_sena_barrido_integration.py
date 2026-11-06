"""C-06 (9.1/9.2): vencimiento de las pre-reservas en espera. ``ahora`` inyectado; sin esperas reales."""

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.core import RegistroAuditoria
from app.pagos.barrido import expirar_pre_reservas
from tests.sena_helpers import (
    fecha_laboral, forzar_vencimiento, iniciar, local, pagos_de, reservar, sembrar_agenda, turno_de,
)

VENCE = datetime(2031, 3, 3, 13, 30, tzinfo=timezone.utc)  # "10:30" hora de la clínica


async def _pre_reserva(client, ids, factory, hhmm="10:00", con_pago=True):
    f = fecha_laboral()
    await sembrar_agenda(factory, ids, f)
    reserva = await reservar(client, ids, local(f, hhmm))
    if con_pago:
        assert (await iniciar(client, reserva, "mercadopago")).status_code == 201
    await forzar_vencimiento(factory, reserva["turno_id"], VENCE)
    return reserva


async def _barrer(factory, ahora):
    async with factory() as s:
        return await expirar_pre_reservas(s, ahora)


async def _auditorias(factory, turno_id):
    async with factory() as s:
        return list((await s.execute(select(RegistroAuditoria).where(
            RegistroAuditoria.entidad == "turno", RegistroAuditoria.entidad_id == str(turno_id)))).scalars().all())


async def test_a_las_10_31_el_vencido_a_las_10_30_pasa_a_cancelado_con_su_pago_vencido(
        client, seed_ids, session_factory, pasarela) -> None:
    reserva = await _pre_reserva(client, seed_ids, session_factory)
    assert await _barrer(session_factory, VENCE + timedelta(minutes=1)) == 1
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "cancelado"
    (pago,) = await pagos_de(session_factory, reserva["turno_id"])
    assert pago.estado == "vencido"
    audit = [a for a in await _auditorias(session_factory, reserva["turno_id"]) if a.datos_despues.get("estado") == "cancelado"]
    assert len(audit) == 1 and audit[0].datos_despues["origen"] == "vencimiento_sena"
    assert audit[0].datos_antes["estado"] == "en_espera"


async def test_a_las_10_29_59_no_cambia_nada(client, seed_ids, session_factory, pasarela) -> None:
    reserva = await _pre_reserva(client, seed_ids, session_factory)
    assert await _barrer(session_factory, VENCE - timedelta(seconds=1)) == 0
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "en_espera"
    (pago,) = await pagos_de(session_factory, reserva["turno_id"])
    assert pago.estado == "pendiente"


async def test_justo_en_el_instante_de_vencimiento_ya_vencio(client, seed_ids, session_factory, pasarela) -> None:
    reserva = await _pre_reserva(client, seed_ids, session_factory)
    assert await _barrer(session_factory, VENCE) == 1
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "cancelado"


async def test_correrlo_dos_veces_no_tiene_efecto_adicional(client, seed_ids, session_factory, pasarela) -> None:
    reserva = await _pre_reserva(client, seed_ids, session_factory)
    assert await _barrer(session_factory, VENCE + timedelta(minutes=1)) == 1
    assert await _barrer(session_factory, VENCE + timedelta(minutes=2)) == 0
    assert len(await _auditorias(session_factory, reserva["turno_id"])) == 2  # creación + vencimiento, sin duplicar


async def test_vence_tambien_una_pre_reserva_sin_pago_iniciado(client, seed_ids, session_factory, pasarela) -> None:
    reserva = await _pre_reserva(client, seed_ids, session_factory, con_pago=False)
    assert await _barrer(session_factory, VENCE + timedelta(minutes=1)) == 1
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "cancelado"
    assert await pagos_de(session_factory, reserva["turno_id"]) == []


async def test_el_barrido_no_toca_turnos_reservados_ni_pre_reservas_vigentes(
        client, seed_ids, session_factory, pasarela) -> None:
    f = fecha_laboral()
    await sembrar_agenda(session_factory, seed_ids, f)
    vigente = await reservar(client, seed_ids, local(f, "11:00"))  # vence en ~30 min desde ahora real
    assert await _barrer(session_factory, datetime.now(timezone.utc)) == 0
    assert (await turno_de(session_factory, vigente["turno_id"])).estado == "en_espera"


async def test_una_pre_reserva_vencida_que_el_barrido_no_toco_igual_se_rechaza_al_iniciar_la_sena(
        client, seed_ids, session_factory, pasarela) -> None:
    f = fecha_laboral()
    await sembrar_agenda(session_factory, seed_ids, f)
    reserva = await reservar(client, seed_ids, local(f, "10:00"))
    await forzar_vencimiento(session_factory, reserva["turno_id"], datetime.now(timezone.utc) - timedelta(seconds=1))
    r = await iniciar(client, reserva, "mercadopago")
    assert r.status_code == 409 and r.json()["motivo"] == "estado_invalido"
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "en_espera"  # el barrido aún no corrió


# --- 9.2 tarea periódica del lifespan -----------------------------------------------------------

async def _esperar(condicion, segundos: float = 6.0) -> bool:
    limite = asyncio.get_running_loop().time() + segundos
    while asyncio.get_running_loop().time() < limite:
        if await condicion():
            return True
        await asyncio.sleep(0.2)
    return False


async def test_la_tarea_del_lifespan_arranca_barre_y_se_cancela_limpia(
        client, seed_ids, session_factory, pasarela, monkeypatch) -> None:
    from app.main import app
    from app.pagos import barrido

    monkeypatch.setenv("SENA_BARRIDO_HABILITADO", "true")
    monkeypatch.setenv("SENA_BARRIDO_SEGUNDOS", "1")
    llamadas: list[datetime] = []
    original = barrido.expirar_pre_reservas

    async def espiado(session, ahora):  # type: ignore[no-untyped-def]
        llamadas.append(ahora)  # prueba que barrió ESTA app (otro backend podría compartir la base local)
        return await original(session, ahora)

    monkeypatch.setattr(barrido, "expirar_pre_reservas", espiado)
    reserva = await _pre_reserva(client, seed_ids, session_factory, con_pago=False)
    await forzar_vencimiento(session_factory, reserva["turno_id"], datetime.now(timezone.utc) - timedelta(minutes=1))

    async with app.router.lifespan_context(app):
        tarea = app.state.barrido_task
        assert tarea is not None and not tarea.done()

        async def barrio_dos_veces() -> bool:
            return len(llamadas) >= 2

        assert await _esperar(barrio_dos_veces)  # periódica: no corre una sola vez
    assert tarea.done() and tarea.cancelled()  # se cancela limpia al apagar la app
    despues = len(llamadas)
    await asyncio.sleep(1.5)
    assert len(llamadas) == despues  # y no sigue barriendo
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "cancelado"


async def test_con_la_bandera_en_false_no_corre_ninguna_tarea(
        client, seed_ids, session_factory, pasarela, monkeypatch) -> None:
    from app import main
    from app.main import app

    creadas: list[object] = []
    monkeypatch.setattr(main, "ciclo_barrido", lambda *a, **k: creadas.append(a) or asyncio.sleep(0))
    async with app.router.lifespan_context(app):
        assert app.state.barrido_task is None
        await asyncio.sleep(0.5)
    assert creadas == []
