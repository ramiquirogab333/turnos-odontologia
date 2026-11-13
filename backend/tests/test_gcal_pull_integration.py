"""C-10 (7.1-7.2): pull incremental y franjas ocupadas de Google (O5, O19). Proveedor falso en memoria."""

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integraciones.gcal.proveedor import SyncTokenVencido
from app.integraciones.gcal.proveedor_falso import ProveedorFalso
from tests.gcal_helpers import AHORA, ciclo, conexion, eventos, sembrar_conexion
from tests.panel_helpers import sembrar_mundo

Factory = async_sessionmaker[AsyncSession]
MANANA = AHORA + timedelta(days=1)


async def _conexion(factory: Factory) -> int:
    mundo = await sembrar_mundo(factory)
    return await sembrar_conexion(factory, mundo["ana"])


async def _franjas(factory: Factory, conexion_id: int) -> list:
    return [e for e in await eventos(factory, conexion_id) if e.origen == "google"]


async def test_un_evento_ocupado_ajeno_se_guarda_como_franja_sin_titulo(session_factory: Factory,
                                                                         proveedor_gcal: ProveedorFalso) -> None:
    conexion_id = await _conexion(session_factory)
    ajeno = proveedor_gcal.crear_ocupado(MANANA, MANANA + timedelta(hours=1), titulo="Evento sintético secreto")
    await ciclo(session_factory, proveedor_gcal)
    [franja] = await _franjas(session_factory, conexion_id)
    assert (franja.google_event_id, franja.inicio, franja.fin, franja.ocupa, franja.turno_id) == (
        ajeno, MANANA, MANANA + timedelta(hours=1), True, None)
    assert "secreto" not in repr(vars(franja))  # la tabla no tiene dónde guardar el título


async def test_un_evento_libre_cancelado_o_rechazado_no_genera_franja(session_factory: Factory,
                                                                       proveedor_gcal: ProveedorFalso) -> None:
    conexion_id = await _conexion(session_factory)
    proveedor_gcal.crear_ocupado(MANANA, MANANA + timedelta(hours=1), ocupa=False)  # transparent o declined
    cancelado = proveedor_gcal.crear_ocupado(MANANA + timedelta(hours=2), MANANA + timedelta(hours=3))
    proveedor_gcal.borrar_externo(cancelado)
    await ciclo(session_factory, proveedor_gcal)
    assert [f for f in await _franjas(session_factory, conexion_id) if f.ocupa] == []


async def test_una_franja_movida_o_borrada_en_google_se_actualiza_o_deja_de_ocupar(session_factory: Factory,
                                                                                    proveedor_gcal: ProveedorFalso) -> None:
    conexion_id = await _conexion(session_factory)
    movida = proveedor_gcal.crear_ocupado(MANANA, MANANA + timedelta(hours=1))
    borrada = proveedor_gcal.crear_ocupado(MANANA + timedelta(hours=3), MANANA + timedelta(hours=4))
    await ciclo(session_factory, proveedor_gcal)
    proveedor_gcal.mover(movida, MANANA + timedelta(hours=2), MANANA + timedelta(hours=3))
    proveedor_gcal.borrar_externo(borrada)
    await ciclo(session_factory, proveedor_gcal)
    por_id = {f.google_event_id: f for f in await _franjas(session_factory, conexion_id)}
    assert (por_id[movida].inicio, por_id[movida].ocupa) == (MANANA + timedelta(hours=2), True)
    assert por_id[borrada].ocupa is False


async def test_un_evento_ocupado_que_pasa_a_libre_deja_de_ocupar(session_factory: Factory,
                                                                  proveedor_gcal: ProveedorFalso) -> None:
    conexion_id = await _conexion(session_factory)
    evento = proveedor_gcal.crear_ocupado(MANANA, MANANA + timedelta(hours=1))
    await ciclo(session_factory, proveedor_gcal)
    proveedor_gcal.eventos[("primary", evento)].ocupa = False
    proveedor_gcal.mover(evento, MANANA, MANANA + timedelta(hours=1))  # registra el cambio
    await ciclo(session_factory, proveedor_gcal)
    assert [f.ocupa for f in await _franjas(session_factory, conexion_id)] == [False]


async def test_la_primera_lectura_se_acota_al_horizonte_y_guarda_el_sync_token(session_factory: Factory,
                                                                               proveedor_gcal: ProveedorFalso) -> None:
    conexion_id = await _conexion(session_factory)
    dentro = proveedor_gcal.crear_ocupado(AHORA + timedelta(days=59), AHORA + timedelta(days=59, hours=1))
    proveedor_gcal.crear_ocupado(AHORA + timedelta(days=90), AHORA + timedelta(days=90, hours=1))
    await ciclo(session_factory, proveedor_gcal)
    assert [f.google_event_id for f in await _franjas(session_factory, conexion_id)] == [dentro]
    assert (await conexion(session_factory, conexion_id)).sync_token


async def test_las_lecturas_siguientes_son_incrementales(session_factory: Factory,
                                                         proveedor_gcal: ProveedorFalso) -> None:
    conexion_id = await _conexion(session_factory)
    proveedor_gcal.crear_ocupado(MANANA, MANANA + timedelta(hours=1))
    await ciclo(session_factory, proveedor_gcal)
    token = (await conexion(session_factory, conexion_id)).sync_token
    nuevo = proveedor_gcal.crear_ocupado(MANANA + timedelta(hours=5), MANANA + timedelta(hours=6))
    await ciclo(session_factory, proveedor_gcal)
    assert (await conexion(session_factory, conexion_id)).sync_token != token
    assert {f.google_event_id for f in await _franjas(session_factory, conexion_id)} >= {nuevo}
    assert len(await _franjas(session_factory, conexion_id)) == 2


async def test_un_sync_token_vencido_relee_el_horizonte_sin_duplicar_y_libera_lo_que_ya_no_esta(
        session_factory: Factory, proveedor_gcal: ProveedorFalso) -> None:
    conexion_id = await _conexion(session_factory)
    queda = proveedor_gcal.crear_ocupado(MANANA, MANANA + timedelta(hours=1))
    desaparece = proveedor_gcal.crear_ocupado(MANANA + timedelta(hours=2), MANANA + timedelta(hours=3))
    await ciclo(session_factory, proveedor_gcal)
    del proveedor_gcal.eventos[("primary", desaparece)]  # Google ya no lo informa en la lectura completa
    proveedor_gcal.invalidar_sync_tokens()
    await ciclo(session_factory, proveedor_gcal)
    franjas = await _franjas(session_factory, conexion_id)
    assert len(franjas) == 2 and {f.google_event_id: f.ocupa for f in franjas} == {queda: True, desaparece: False}
    assert (await conexion(session_factory, conexion_id)).sync_token


async def test_un_evento_propio_de_otra_conexion_no_se_toma_como_franja(session_factory: Factory,
                                                                         proveedor_gcal: ProveedorFalso) -> None:
    conexion_id = await _conexion(session_factory)
    proveedor_gcal.crear_ocupado(MANANA, MANANA + timedelta(hours=1))
    proveedor_gcal.eventos[("primary", next(iter(e for (_, e) in proveedor_gcal.eventos)))].propias = {
        "turnos_sistema": "1", "turno_id": "999"}
    await ciclo(session_factory, proveedor_gcal)
    assert await _franjas(session_factory, conexion_id) == []
