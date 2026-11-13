"""C-10 (9.4): la API nunca llama a Google; el notificador solo marca pendiente. Sintético (R19)."""

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.gestion.deps import get_notificador
from app.gestion.eventos import EventoTurno
from app.integraciones.gcal.notificador import NotificadorCalendario
from app.integraciones.gcal.proveedor import ErrorTransitorio
from app.integraciones.gcal.proveedor_falso import ProveedorFalso
from app.notificaciones.notificador import NotificadorCompuesto, NotificadorRecordatorios
from tests.gcal_helpers import AHORA, ciclo, conexion, eventos, poner_conexion, sembrar_conexion
from tests.panel_helpers import insertar_turno, sembrar_mundo
from tests.sena_helpers import cabecera, local, turno_de
from tests.test_sena_transiciones_integration import _reservado_con_sena

Factory = async_sessionmaker[AsyncSession]
URL = "/api/public/gestion"
MANANA = AHORA + timedelta(days=1)


def _evento(turno_id: int, profesional_id: int, tipo: str = "turno_reprogramado") -> EventoTurno:
    return EventoTurno(tipo=tipo, turno_id=turno_id, profesional_id=profesional_id, inicio_anterior=MANANA,  # type: ignore[arg-type]
                       fin_anterior=MANANA + timedelta(minutes=30), inicio_nuevo=MANANA + timedelta(hours=2),
                       fin_nuevo=MANANA + timedelta(hours=2, minutes=30), ocurrido_en=AHORA)


async def test_el_notificador_marca_pendiente_el_evento_y_limpia_la_espera_de_la_conexion(
        session_factory: Factory, proveedor_gcal: ProveedorFalso) -> None:
    mundo = await sembrar_mundo(session_factory)
    conexion_id = await sembrar_conexion(session_factory, mundo["ana"])
    turno = await insertar_turno(session_factory, mundo, MANANA)
    await ciclo(session_factory, proveedor_gcal)
    await poner_conexion(session_factory, conexion_id, proximo_intento_en=AHORA + timedelta(minutes=60),
                         fallos_consecutivos=4)
    llamadas = list(proveedor_gcal.llamadas)
    await NotificadorCalendario(session_factory).publicar(_evento(turno, mundo["ana"]))
    [vinculo] = await eventos(session_factory, conexion_id)
    assert vinculo.estado == "pendiente" and (await conexion(session_factory, conexion_id)).proximo_intento_en is None
    assert proveedor_gcal.llamadas == llamadas  # solo toca la base, nunca Google


async def test_un_turno_de_una_profesional_sin_conexion_no_encola_nada(session_factory: Factory,
                                                                        proveedor_gcal: ProveedorFalso) -> None:
    mundo = await sembrar_mundo(session_factory)
    turno = await insertar_turno(session_factory, mundo, MANANA, prof="bruno")
    await NotificadorCalendario(session_factory).publicar(_evento(turno, mundo["bruno"]))
    assert await eventos(session_factory) == []


async def test_get_notificador_devuelve_el_compuesto_con_recordatorios_y_calendario() -> None:
    compuesto = get_notificador()
    assert isinstance(compuesto, NotificadorCompuesto)
    assert [type(n) for n in compuesto._notificadores] == [NotificadorRecordatorios, NotificadorCalendario]  # noqa: SLF001


async def test_cancelar_con_google_caido_responde_200_y_el_evento_se_borra_cuando_vuelve(
        client, seed_ids, session_factory: Factory, proveedor_gcal: ProveedorFalso, pasarela, reloj) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    conexion_id = await sembrar_conexion(session_factory, seed_ids["profesional_id"])
    await ciclo(session_factory, proveedor_gcal, ahora=inicio - timedelta(days=3))
    assert len(proveedor_gcal.vigentes()) == 1
    proveedor_gcal.fallar(ErrorTransitorio(503))  # Google sin respuesta
    llamadas = len(proveedor_gcal.llamadas)
    reloj(inicio - timedelta(hours=30))
    r = await client.post(URL + "/cancelar", headers=cabecera(reserva))
    assert r.status_code == 200 and len(proveedor_gcal.llamadas) == llamadas  # la API no llamó a Google
    assert await ciclo(session_factory, proveedor_gcal, ahora=inicio - timedelta(hours=29)) == 0  # Google sigue caído
    assert await ciclo(session_factory, proveedor_gcal, ahora=inicio - timedelta(hours=28)) == 1
    assert proveedor_gcal.vigentes() == []
    assert [e.estado for e in await eventos(session_factory, conexion_id)] == ["borrado"]


async def test_si_el_aviso_al_calendario_falla_la_reprogramacion_responde_200_y_el_ciclo_mueve_el_evento(
        client, seed_ids, session_factory: Factory, proveedor_gcal: ProveedorFalso, pasarela, reloj) -> None:
    from app.main import app

    class Caido:
        async def publicar(self, evento: EventoTurno) -> None:
            raise RuntimeError("marcar el evento falló (simulado)")

    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    await sembrar_conexion(session_factory, seed_ids["profesional_id"])
    await ciclo(session_factory, proveedor_gcal, ahora=inicio - timedelta(days=6))
    app.dependency_overrides[get_notificador] = lambda: Caido()
    try:
        reloj(inicio - timedelta(days=5))
        nuevo = local(inicio.date(), "12:00")
        r = await client.post(URL + "/reprogramar", json={"inicio": nuevo.isoformat()}, headers=cabecera(reserva))
    finally:
        app.dependency_overrides.pop(get_notificador, None)
    assert r.status_code == 200 and (await turno_de(session_factory, reserva["turno_id"])).inicio == nuevo
    await ciclo(session_factory, proveedor_gcal, ahora=inicio - timedelta(days=5))
    assert [e.inicio for e in proveedor_gcal.vigentes()] == [nuevo] and proveedor_gcal.llamadas.count("insertar") == 1


async def test_reservar_y_cancelar_para_una_profesional_sin_conexion_no_llama_a_google(
        client, seed_ids, session_factory: Factory, proveedor_gcal: ProveedorFalso, pasarela, reloj) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    reloj(inicio - timedelta(hours=40))
    assert (await client.post(URL + "/cancelar", headers=cabecera(reserva))).status_code == 200
    assert await eventos(session_factory) == [] and proveedor_gcal.llamadas == []
