"""C-10 (6.1-6.6): push por reconciliación (turno -> evento de Google). Reloj fijo, proveedor falso en memoria."""

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integraciones.gcal.contenido import armar_contenido, id_evento
from app.integraciones.gcal.proveedor import ErrorTransitorio, EtagDesactualizado
from app.integraciones.gcal.proveedor_falso import ProveedorFalso
from tests.gcal_helpers import AHORA, ciclo, conflictos, eventos, sembrar_conexion
from tests.panel_helpers import insertar_turno, sembrar_mundo
from tests.recordatorios_helpers import poner_turno

Factory = async_sessionmaker[AsyncSession]
MANANA = AHORA + timedelta(days=1)


def _escrituras(proveedor: ProveedorFalso) -> int:
    return sum(proveedor.llamadas.count(m) for m in ("insertar", "actualizar", "borrar"))


async def _mundo(factory: Factory) -> tuple[dict[str, int], int]:
    mundo = await sembrar_mundo(factory)
    return mundo, await sembrar_conexion(factory, mundo["ana"])


# --- 6.1 Qué turnos tienen evento ---------------------------------------------------------------------------------

@pytest.mark.parametrize("estado,origen", [("reservado", "web"), ("reservado", "manual"), ("confirmado", "web")])
async def test_los_turnos_que_bloquean_agenda_tienen_un_evento_sin_datos_del_paciente(
        session_factory: Factory, proveedor_gcal: ProveedorFalso, estado: str, origen: str) -> None:
    mundo, conexion = await _mundo(session_factory)
    turno = await insertar_turno(session_factory, mundo, MANANA, estado=estado, origen=origen,
                                 nombre="Paciente Ficticio", telefono="+5491100000000")
    await ciclo(session_factory, proveedor_gcal)
    [evento] = proveedor_gcal.vigentes()
    assert evento.titulo == "Turno · Limpieza dental" and evento.inicio == MANANA
    assert evento.fin == MANANA + timedelta(minutes=30) and "Sillón 1" in evento.descripcion
    assert "Paciente Ficticio" not in f"{evento.titulo}{evento.descripcion}" and "+5491100000000" not in evento.descripcion
    [vinculo] = await eventos(session_factory, conexion)
    assert (vinculo.turno_id, vinculo.origen, vinculo.estado, vinculo.generacion) == (turno, "sistema", "sincronizado", 0)
    assert vinculo.google_event_id == id_evento(turno, conexion, 0) and vinculo.etag


async def test_una_pre_reserva_y_un_vencido_nunca_tienen_evento(session_factory: Factory,
                                                                proveedor_gcal: ProveedorFalso) -> None:
    mundo, _ = await _mundo(session_factory)
    await insertar_turno(session_factory, mundo, MANANA, estado="en_espera", vence=MANANA)
    await insertar_turno(session_factory, mundo, MANANA + timedelta(hours=1), estado="cancelado")
    for _ in range(3):
        await ciclo(session_factory, proveedor_gcal)
    assert proveedor_gcal.vigentes() == [] and _escrituras(proveedor_gcal) == 0


async def test_el_horizonte_incluye_59_dias_y_excluye_61_hasta_que_entra(session_factory: Factory,
                                                                        proveedor_gcal: ProveedorFalso) -> None:
    mundo, conexion = await _mundo(session_factory)
    cerca = await insertar_turno(session_factory, mundo, AHORA + timedelta(days=59), origen="manual")
    lejos = await insertar_turno(session_factory, mundo, AHORA + timedelta(days=61), origen="manual")
    await ciclo(session_factory, proveedor_gcal)
    assert {e.turno_id for e in await eventos(session_factory, conexion)} == {cerca}
    await ciclo(session_factory, proveedor_gcal, ahora=AHORA + timedelta(days=2))  # el de 61 días ya entra
    assert {e.turno_id for e in await eventos(session_factory, conexion)} == {cerca, lejos}


async def test_una_conexion_que_no_esta_activa_no_se_sincroniza(session_factory: Factory,
                                                                proveedor_gcal: ProveedorFalso) -> None:
    mundo = await sembrar_mundo(session_factory)
    await sembrar_conexion(session_factory, mundo["ana"], estado="desconectada")
    await insertar_turno(session_factory, mundo, MANANA)
    assert await ciclo(session_factory, proveedor_gcal) == 0 and proveedor_gcal.llamadas == []


# --- 6.3 Cancelar y reprogramar -----------------------------------------------------------------------------------

async def test_cancelar_borra_el_evento_y_deja_el_vinculo_borrado(session_factory: Factory,
                                                                  proveedor_gcal: ProveedorFalso) -> None:
    mundo, conexion = await _mundo(session_factory)
    turno = await insertar_turno(session_factory, mundo, MANANA)
    await ciclo(session_factory, proveedor_gcal)
    await poner_turno(session_factory, turno, estado="cancelado")
    await ciclo(session_factory, proveedor_gcal)
    assert proveedor_gcal.vigentes() == []
    assert [e.estado for e in await eventos(session_factory, conexion)] == ["borrado"]
    antes = _escrituras(proveedor_gcal)
    await ciclo(session_factory, proveedor_gcal)
    assert _escrituras(proveedor_gcal) == antes  # nada más que hacer


@pytest.mark.parametrize("nuevo", [MANANA + timedelta(hours=6), AHORA + timedelta(days=70)])
async def test_reprogramar_mueve_el_mismo_evento_aunque_el_aviso_se_pierda_o_salga_del_horizonte(
        session_factory: Factory, proveedor_gcal: ProveedorFalso, nuevo) -> None:
    mundo, conexion = await _mundo(session_factory)
    turno = await insertar_turno(session_factory, mundo, MANANA)
    await ciclo(session_factory, proveedor_gcal)
    await poner_turno(session_factory, turno, inicio=nuevo, fin=nuevo + timedelta(minutes=30))  # sin avisar a nadie
    await ciclo(session_factory, proveedor_gcal)
    [evento] = proveedor_gcal.vigentes()
    assert evento.inicio == nuevo and proveedor_gcal.llamadas.count("insertar") == 1
    [vinculo] = await eventos(session_factory, conexion)
    assert (vinculo.inicio, vinculo.estado) == (nuevo, "sincronizado")


async def test_renombrar_el_tratamiento_actualiza_el_titulo(session_factory: Factory,
                                                            proveedor_gcal: ProveedorFalso) -> None:
    from sqlalchemy import update

    from app.turnos.models import Tratamiento

    mundo, _ = await _mundo(session_factory)
    await insertar_turno(session_factory, mundo, MANANA)
    await ciclo(session_factory, proveedor_gcal)
    async with session_factory() as s:
        await s.execute(update(Tratamiento).values(nombre="Limpieza profunda"))
        await s.commit()
    await ciclo(session_factory, proveedor_gcal)
    assert [e.titulo for e in proveedor_gcal.vigentes()] == ["Turno · Limpieza profunda"]


async def test_un_turno_interno_sin_paciente_ni_codigo_tiene_evento_con_el_mismo_formato(
        session_factory: Factory, proveedor_gcal: ProveedorFalso) -> None:
    mundo, _ = await _mundo(session_factory)
    await insertar_turno(session_factory, mundo, MANANA, origen="manual", nombre=None, telefono=None, con_codigo=False)
    await ciclo(session_factory, proveedor_gcal)
    [evento] = proveedor_gcal.vigentes()
    assert evento.titulo.startswith("Turno · ") and "gestion" not in evento.descripcion


# --- 6.4 Ausente y atendido ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("destino", ["atendido", "ausente"])
async def test_ausente_y_atendido_conservan_el_evento_sin_llamadas(session_factory: Factory,
                                                                    proveedor_gcal: ProveedorFalso,
                                                                    destino: str) -> None:
    mundo, conexion = await _mundo(session_factory)
    turno = await insertar_turno(session_factory, mundo, MANANA, estado="confirmado")
    await ciclo(session_factory, proveedor_gcal)
    llamadas = _escrituras(proveedor_gcal)
    await poner_turno(session_factory, turno, estado=destino)
    await ciclo(session_factory, proveedor_gcal)
    assert _escrituras(proveedor_gcal) == llamadas and len(proveedor_gcal.vigentes()) == 1
    assert [e.estado for e in await eventos(session_factory, conexion)] == ["sincronizado"]


async def test_deshacer_un_atendido_no_crea_otro_evento(session_factory: Factory,
                                                         proveedor_gcal: ProveedorFalso) -> None:
    mundo, conexion = await _mundo(session_factory)
    turno = await insertar_turno(session_factory, mundo, MANANA)
    await ciclo(session_factory, proveedor_gcal)
    await poner_turno(session_factory, turno, estado="atendido")
    await ciclo(session_factory, proveedor_gcal)
    await poner_turno(session_factory, turno, estado="reservado")
    await ciclo(session_factory, proveedor_gcal)
    assert len(await eventos(session_factory, conexion)) == 1 and proveedor_gcal.llamadas.count("insertar") == 1


# --- 6.5 Idempotencia ---------------------------------------------------------------------------------------------

async def test_si_el_evento_ya_existia_en_google_se_vincula_sin_duplicar(session_factory: Factory,
                                                                         proveedor_gcal: ProveedorFalso) -> None:
    """El worker creó el evento y se cayó antes de guardar el vínculo."""
    from zoneinfo import ZoneInfo

    mundo, conexion = await _mundo(session_factory)
    turno = await insertar_turno(session_factory, mundo, MANANA)
    evento_id = id_evento(turno, conexion, 0)
    await proveedor_gcal.insertar("x", "primary", evento_id, armar_contenido(
        turno_id=turno, tratamiento="Limpieza dental", sillon="Sillón 1", inicio=MANANA,
        fin=MANANA + timedelta(minutes=30), zona=ZoneInfo("America/Argentina/Buenos_Aires"), url_panel="http://x"))
    await ciclo(session_factory, proveedor_gcal)
    [vinculo] = await eventos(session_factory, conexion)
    assert vinculo.google_event_id == evento_id and vinculo.estado == "sincronizado" and vinculo.etag
    assert len(proveedor_gcal.vigentes()) == 1


async def test_dos_ciclos_concurrentes_dejan_un_solo_evento(session_factory: Factory,
                                                             proveedor_gcal: ProveedorFalso) -> None:
    mundo, conexion = await _mundo(session_factory)
    await insertar_turno(session_factory, mundo, MANANA)
    resultados = await asyncio.gather(ciclo(session_factory, proveedor_gcal), ciclo(session_factory, proveedor_gcal))
    assert len(proveedor_gcal.vigentes()) == 1 and len(await eventos(session_factory, conexion)) == 1
    assert sorted(resultados) in ([0, 1], [1, 1])  # uno procesa; el otro la saltea o ya la encuentra al día


async def test_dos_ciclos_seguidos_no_repiten_llamadas(session_factory: Factory, proveedor_gcal: ProveedorFalso) -> None:
    mundo, _ = await _mundo(session_factory)
    await insertar_turno(session_factory, mundo, MANANA)
    await ciclo(session_factory, proveedor_gcal)
    antes = _escrituras(proveedor_gcal)
    await ciclo(session_factory, proveedor_gcal)
    assert _escrituras(proveedor_gcal) == antes == 1


# --- 6.6 No sobrescribir ------------------------------------------------------------------------------------------

async def test_con_un_conflicto_abierto_el_push_no_escribe_ese_evento(session_factory: Factory,
                                                                      proveedor_gcal: ProveedorFalso) -> None:
    mundo, conexion = await _mundo(session_factory)
    turno = await insertar_turno(session_factory, mundo, MANANA)
    await ciclo(session_factory, proveedor_gcal)
    [vinculo] = await eventos(session_factory, conexion)
    nuevo = MANANA + timedelta(hours=2)
    proveedor_gcal.mover(vinculo.google_event_id, nuevo, nuevo + timedelta(minutes=30))
    await ciclo(session_factory, proveedor_gcal)
    assert [c.tipo for c in await conflictos(session_factory, "abierto")] == ["movido_en_google"]
    antes = _escrituras(proveedor_gcal)
    await poner_turno(session_factory, turno, inicio=MANANA + timedelta(hours=4),
                      fin=MANANA + timedelta(hours=4, minutes=30))
    await ciclo(session_factory, proveedor_gcal)
    assert _escrituras(proveedor_gcal) == antes and proveedor_gcal.vigentes()[0].inicio == nuevo


async def test_un_etag_desactualizado_en_el_patch_no_escribe_y_no_rompe_el_ciclo(
        session_factory: Factory, proveedor_gcal: ProveedorFalso) -> None:
    mundo, conexion = await _mundo(session_factory)
    turno = await insertar_turno(session_factory, mundo, MANANA)
    await ciclo(session_factory, proveedor_gcal)
    await poner_turno(session_factory, turno, inicio=MANANA + timedelta(hours=3),
                      fin=MANANA + timedelta(hours=3, minutes=30))
    proveedor_gcal.fallar(EtagDesactualizado(), en=("actualizar",))
    assert await ciclo(session_factory, proveedor_gcal) == 1  # la conexión terminó bien
    assert proveedor_gcal.vigentes()[0].inicio == MANANA
    await ciclo(session_factory, proveedor_gcal)  # el siguiente ciclo sí lo mueve
    assert proveedor_gcal.vigentes()[0].inicio == MANANA + timedelta(hours=3)


async def test_un_vinculo_desvinculado_no_se_vuelve_a_tocar(session_factory: Factory,
                                                             proveedor_gcal: ProveedorFalso) -> None:
    from sqlalchemy import update

    from app.integraciones.gcal.models import EventoCalendar

    mundo, conexion = await _mundo(session_factory)
    turno = await insertar_turno(session_factory, mundo, MANANA)
    await ciclo(session_factory, proveedor_gcal)
    async with session_factory() as s:
        await s.execute(update(EventoCalendar).values(estado="desvinculado"))
        await s.commit()
    await poner_turno(session_factory, turno, estado="cancelado")
    antes = _escrituras(proveedor_gcal)
    await ciclo(session_factory, proveedor_gcal)
    assert _escrituras(proveedor_gcal) == antes and len(proveedor_gcal.vigentes()) == 1


async def test_un_error_transitorio_en_el_insert_se_reintenta_en_el_ciclo_siguiente(
        session_factory: Factory, proveedor_gcal: ProveedorFalso) -> None:
    mundo, conexion = await _mundo(session_factory)
    await insertar_turno(session_factory, mundo, MANANA)
    proveedor_gcal.fallar(ErrorTransitorio(503), en=("insertar",))
    assert await ciclo(session_factory, proveedor_gcal) == 0 and proveedor_gcal.vigentes() == []
    await ciclo(session_factory, proveedor_gcal, ahora=AHORA + timedelta(minutes=2))
    assert len(proveedor_gcal.vigentes()) == 1
