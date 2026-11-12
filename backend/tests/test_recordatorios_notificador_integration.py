"""C-09 (6.1-6.3, D6): la cancelación y la reprogramación anulan el recordatorio del horario anterior. Sintético (R19)."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.gestion.deps import get_notificador
from app.gestion.eventos import EventoTurno
from app.notificaciones.notificador import NotificadorCompuesto, NotificadorRecordatorios
from app.pagos.service import cambiar_estado_turno
from tests.recordatorios_helpers import AHORA, ciclo, recordatorios, sembrar_recordatorio
from tests.panel_helpers import insertar_turno, sembrar_mundo
from tests.sena_helpers import cabecera, local, pagos_de, turno_de
from tests.test_sena_transiciones_integration import _reservado_con_sena

Factory = async_sessionmaker[AsyncSession]
URL = "/api/public/gestion"


def _evento(tipo: str, turno_id: int, inicio_anterior: datetime, inicio_nuevo: datetime | None = None) -> EventoTurno:
    return EventoTurno(tipo=tipo, turno_id=turno_id, profesional_id=1, inicio_anterior=inicio_anterior,  # type: ignore[arg-type]
                       fin_anterior=inicio_anterior + timedelta(minutes=30), inicio_nuevo=inicio_nuevo,
                       fin_nuevo=inicio_nuevo + timedelta(minutes=30) if inicio_nuevo else None, ocurrido_en=AHORA)


# --- 6.1 Notificador --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("estado", ["pendiente", "enviado", "fallido", "confirmado"])
async def test_turno_cancelado_anula_los_recordatorios_vigentes_del_horario_anterior(
        session_factory: Factory, estado: str) -> None:
    mundo = await sembrar_mundo(session_factory)
    inicio = AHORA + timedelta(hours=40)
    turno = await insertar_turno(session_factory, mundo, inicio, estado="cancelado")
    await sembrar_recordatorio(session_factory, turno, inicio, estado)
    await NotificadorRecordatorios(session_factory).publicar(_evento("turno_cancelado", turno, inicio))
    [r] = await recordatorios(session_factory, turno)
    assert (r.estado, r.motivo, r.confirmado_en) == ("anulado", "turno_cancelado", None)


async def test_turno_reprogramado_anula_solo_el_horario_anterior(session_factory: Factory) -> None:
    mundo = await sembrar_mundo(session_factory)
    viejo, nuevo = AHORA + timedelta(hours=40), AHORA + timedelta(hours=60)
    turno = await insertar_turno(session_factory, mundo, nuevo)
    await sembrar_recordatorio(session_factory, turno, viejo, "enviado")
    await sembrar_recordatorio(session_factory, turno, nuevo, "pendiente")
    await NotificadorRecordatorios(session_factory).publicar(_evento("turno_reprogramado", turno, viejo, nuevo))
    vistos = {r.turno_inicio: (r.estado, r.motivo) for r in await recordatorios(session_factory, turno)}
    assert vistos == {viejo: ("anulado", "turno_reprogramado"), nuevo: ("pendiente", None)}


async def test_un_evento_de_un_turno_sin_recordatorios_no_falla(session_factory: Factory) -> None:
    mundo = await sembrar_mundo(session_factory)
    turno = await insertar_turno(session_factory, mundo, AHORA + timedelta(hours=40))
    await NotificadorRecordatorios(session_factory).publicar(_evento("turno_cancelado", turno, AHORA))
    assert await recordatorios(session_factory, turno) == []


async def test_el_compuesto_publica_en_todos_aunque_uno_falle_y_avisa_del_error() -> None:
    class Espia:
        def __init__(self) -> None:
            self.vistos: list[EventoTurno] = []

        async def publicar(self, evento: EventoTurno) -> None:
            self.vistos.append(evento)

    class Roto:
        async def publicar(self, evento: EventoTurno) -> None:
            raise RuntimeError("caído")

    a, b = Espia(), Espia()
    evento = _evento("turno_cancelado", 1, AHORA)
    with pytest.raises(RuntimeError):
        await NotificadorCompuesto([a, Roto(), b]).publicar(evento)
    assert a.vistos == [evento] and b.vistos == [evento]  # el resto igual recibió el evento


# --- 6.3 End-to-end por API (sin override del notificador: se usa el real) --------------------------------------

async def test_cancelar_desde_la_gestion_con_40h_deja_la_sena_a_reembolsar_y_anula_el_recordatorio(
        client, seed_ids, session_factory, pasarela, reloj) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    await sembrar_recordatorio(session_factory, reserva["turno_id"], inicio, "enviado")
    reloj(inicio - timedelta(hours=40))
    r = await client.post(URL + "/cancelar", headers=cabecera(reserva))
    assert r.status_code == 200 and r.json()["estado_sena"] == "a_reembolsar"
    [rec] = await recordatorios(session_factory, reserva["turno_id"])
    assert (rec.estado, rec.motivo) == ("anulado", "turno_cancelado")


async def test_cancelar_con_23h59_es_409_fuera_de_plazo_y_el_recordatorio_sigue_enviado(
        client, seed_ids, session_factory, pasarela, reloj) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    await sembrar_recordatorio(session_factory, reserva["turno_id"], inicio, "enviado")
    reloj(inicio - timedelta(hours=23, minutes=59))
    r = await client.post(URL + "/cancelar", headers=cabecera(reserva))
    assert r.status_code == 409 and r.json()["motivo"] == "fuera_de_plazo"
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "reservado"
    [rec] = await recordatorios(session_factory, reserva["turno_id"])
    assert rec.estado == "enviado"


async def test_reprogramar_un_confirmado_lo_deja_reservado_y_le_genera_un_recordatorio_nuevo(
        client, seed_ids, session_factory, pasarela, reloj) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    async with session_factory() as s:
        await cambiar_estado_turno(s, reserva["turno_id"], "confirmado", None)
    await sembrar_recordatorio(session_factory, reserva["turno_id"], inicio, "confirmado")
    reloj(inicio - timedelta(days=5))
    nuevo = local(inicio.date(), "12:00")
    r = await client.post(URL + "/reprogramar", json={"inicio": nuevo.isoformat()}, headers=cabecera(reserva))
    assert r.status_code == 200 and r.json()["estado"] == "reservado"
    viejo, = [x for x in await recordatorios(session_factory, reserva["turno_id"])]
    assert (viejo.estado, viejo.motivo, viejo.turno_inicio) == ("anulado", "turno_reprogramado", inicio)
    # El horario nuevo cae dentro de la anticipación en el reloj del trabajo: se genera uno pendiente.
    await ciclo(session_factory, ahora=nuevo - timedelta(hours=30))
    vistos = {x.turno_inicio: x.estado for x in await recordatorios(session_factory, reserva["turno_id"])}
    assert vistos == {inicio: "anulado", nuevo: "pendiente"}


async def test_si_el_notificador_falla_la_cancelacion_igual_es_200_y_el_siguiente_ciclo_lo_corrige(
        client, seed_ids, session_factory, pasarela, reloj) -> None:
    from app.main import app

    class Caido:
        async def publicar(self, evento: EventoTurno) -> None:
            raise RuntimeError("publicador caído (simulado)")

    app.dependency_overrides[get_notificador] = lambda: Caido()
    try:
        reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
        await sembrar_recordatorio(session_factory, reserva["turno_id"], inicio, "enviado")
        reloj(inicio - timedelta(hours=48))
        r = await client.post(URL + "/cancelar", headers=cabecera(reserva))
    finally:
        app.dependency_overrides.pop(get_notificador, None)
    assert r.status_code == 200
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "cancelado"
    assert (await pagos_de(session_factory, reserva["turno_id"]))[0].estado == "a_reembolsar"
    [rec] = await recordatorios(session_factory, reserva["turno_id"])
    assert rec.estado == "enviado"  # la anulación inmediata no corrió
    await ciclo(session_factory, ahora=datetime.now(timezone.utc))
    [rec] = await recordatorios(session_factory, reserva["turno_id"])
    assert (rec.estado, rec.motivo) == ("anulado", "turno_cancelado")
