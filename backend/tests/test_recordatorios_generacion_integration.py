"""C-09 (4.1-4.3): generación de recordatorios con ``ahora`` fijo contra PostgreSQL real. Datos sintéticos (R19)."""

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.clinica_helpers import crear_paciente
from tests.panel_helpers import insertar_turno, sembrar_mundo
from tests.recordatorios_helpers import AHORA, ciclo, poner_turno, recordatorios, sembrar_recordatorio

Factory = async_sessionmaker[AsyncSession]


async def _mundo(factory: Factory) -> dict[str, int]:
    return await sembrar_mundo(factory)


# --- Solo los turnos reservados reciben recordatorio ------------------------------------------------------------

async def test_un_turno_reservado_dentro_de_la_anticipacion_recibe_un_recordatorio_pendiente(
        session_factory: Factory) -> None:
    mundo = await _mundo(session_factory)
    inicio = AHORA + timedelta(hours=30)
    turno = await insertar_turno(session_factory, mundo, inicio)
    resumen = await ciclo(session_factory)
    [r] = await recordatorios(session_factory, turno)
    assert (r.estado, r.canal, r.turno_inicio, r.intentos_fallidos) == ("pendiente", "whatsapp", inicio, 0)
    assert resumen.generados == 1


async def test_una_pre_reserva_en_espera_no_recibe_y_al_acreditarse_el_siguiente_ciclo_la_genera(
        session_factory: Factory) -> None:
    mundo = await _mundo(session_factory)
    turno = await insertar_turno(session_factory, mundo, AHORA + timedelta(hours=30), estado="en_espera")
    await ciclo(session_factory)
    assert await recordatorios(session_factory, turno) == []
    await poner_turno(session_factory, turno, estado="reservado", en_espera_vence_en=None)
    await ciclo(session_factory)
    [r] = await recordatorios(session_factory, turno)
    assert r.estado == "pendiente"


@pytest.mark.parametrize("estado", ["confirmado", "cancelado", "ausente", "atendido"])
async def test_los_otros_estados_no_reciben_recordatorio(session_factory: Factory, estado: str) -> None:
    mundo = await _mundo(session_factory)
    turno = await insertar_turno(session_factory, mundo, AHORA + timedelta(hours=30), estado=estado)
    await ciclo(session_factory)
    assert await recordatorios(session_factory, turno) == []


async def test_el_alta_manual_reservada_sin_sena_si_recibe_recordatorio(session_factory: Factory) -> None:
    mundo = await _mundo(session_factory)
    turno = await insertar_turno(session_factory, mundo, AHORA + timedelta(hours=20), origen="manual")
    await ciclo(session_factory)
    [r] = await recordatorios(session_factory, turno)
    assert r.estado == "pendiente"


async def test_el_limite_de_la_anticipacion_es_inclusivo_con_48_horas_exactas(session_factory: Factory) -> None:
    mundo = await _mundo(session_factory)
    justo = await insertar_turno(session_factory, mundo, AHORA + timedelta(hours=48))
    pasado = await insertar_turno(session_factory, mundo, AHORA + timedelta(hours=48, minutes=1), prof="bruno", sillon="s2")
    await ciclo(session_factory)
    assert [r.estado for r in await recordatorios(session_factory, justo)] == ["pendiente"]
    assert await recordatorios(session_factory, pasado) == []


# --- Turnos reservados tarde ------------------------------------------------------------------------------------

async def test_un_turno_para_manana_reservado_hoy_recibe_su_recordatorio_en_el_siguiente_ciclo(
        session_factory: Factory) -> None:
    mundo = await _mundo(session_factory)
    turno = await insertar_turno(session_factory, mundo, AHORA + timedelta(hours=25))
    await ciclo(session_factory)
    assert [r.estado for r in await recordatorios(session_factory, turno)] == ["pendiente"]


async def test_un_turno_que_ya_empezo_y_nunca_tuvo_recordatorio_no_recibe_ninguno(session_factory: Factory) -> None:
    mundo = await _mundo(session_factory)
    turno = await insertar_turno(session_factory, mundo, AHORA - timedelta(minutes=5))
    await ciclo(session_factory)
    assert await recordatorios(session_factory, turno) == []


async def test_el_instante_exacto_del_inicio_no_genera(session_factory: Factory) -> None:
    mundo = await _mundo(session_factory)
    turno = await insertar_turno(session_factory, mundo, AHORA)
    await ciclo(session_factory)
    assert await recordatorios(session_factory, turno) == []


async def test_un_recordatorio_pendiente_o_fallido_se_anula_cuando_el_turno_empieza(session_factory: Factory) -> None:
    mundo = await _mundo(session_factory)
    inicio = AHORA - timedelta(seconds=1)
    pendiente = await insertar_turno(session_factory, mundo, inicio)
    fallido = await insertar_turno(session_factory, mundo, inicio, prof="bruno", sillon="s2")
    await sembrar_recordatorio(session_factory, pendiente, inicio)
    await sembrar_recordatorio(session_factory, fallido, inicio, "fallido")
    await ciclo(session_factory)
    for turno in (pendiente, fallido):
        [r] = await recordatorios(session_factory, turno)
        assert (r.estado, r.motivo) == ("anulado", "turno_iniciado")


async def test_un_recordatorio_enviado_de_un_turno_que_empezo_conserva_su_estado(session_factory: Factory) -> None:
    mundo = await _mundo(session_factory)
    inicio = AHORA - timedelta(minutes=1)
    turno = await insertar_turno(session_factory, mundo, inicio)
    await sembrar_recordatorio(session_factory, turno, inicio, "enviado")
    await ciclo(session_factory)
    assert [r.estado for r in await recordatorios(session_factory, turno)] == ["enviado"]


# --- Teléfono ---------------------------------------------------------------------------------------------------

async def test_el_telefono_del_turno_deja_el_recordatorio_pendiente(session_factory: Factory) -> None:
    mundo = await _mundo(session_factory)
    turno = await insertar_turno(session_factory, mundo, AHORA + timedelta(hours=30), telefono="+5491100000001")
    await ciclo(session_factory)
    [r] = await recordatorios(session_factory, turno)
    assert (r.estado, r.motivo) == ("pendiente", None)


async def test_sin_telefono_el_recordatorio_nace_fallido_sin_reintentos(session_factory: Factory) -> None:
    mundo = await _mundo(session_factory)
    turno = await insertar_turno(session_factory, mundo, AHORA + timedelta(hours=30), telefono=None)
    resumen = await ciclo(session_factory)
    [r] = await recordatorios(session_factory, turno)
    assert (r.estado, r.motivo, r.intentos_fallidos, r.proximo_intento_en) == ("fallido", "sin_telefono", 0, None)
    assert resumen.sin_telefono == 1


async def test_el_telefono_solo_en_la_ficha_del_paciente_alcanza(session_factory: Factory) -> None:
    mundo = await _mundo(session_factory)
    paciente = await crear_paciente(session_factory, nombre="Lucía", apellido="Ficticia", telefono="+5491100000002")
    turno = await insertar_turno(session_factory, mundo, AHORA + timedelta(hours=30), telefono=None,
                                 paciente_id=paciente)
    await ciclo(session_factory)
    [r] = await recordatorios(session_factory, turno)
    assert r.estado == "pendiente"


async def test_una_ficha_con_telefono_que_no_es_e164_sin_telefono_en_el_turno_queda_fallida(
        session_factory: Factory) -> None:
    mundo = await _mundo(session_factory)
    paciente = await crear_paciente(session_factory, telefono="011 4444-5555")
    turno = await insertar_turno(session_factory, mundo, AHORA + timedelta(hours=30), telefono=None,
                                 paciente_id=paciente)
    await ciclo(session_factory)
    [r] = await recordatorios(session_factory, turno)
    assert (r.estado, r.motivo) == ("fallido", "sin_telefono")


# --- Un solo recordatorio vigente por horario -------------------------------------------------------------------

async def test_ciclos_repetidos_no_duplican_ni_cambian_un_recordatorio_enviado(session_factory: Factory) -> None:
    mundo = await _mundo(session_factory)
    inicio = AHORA + timedelta(hours=30)
    turno = await insertar_turno(session_factory, mundo, inicio)
    rid = await sembrar_recordatorio(session_factory, turno, inicio, "enviado")
    antes = (await recordatorios(session_factory, turno))[0]
    for _ in range(3):
        await ciclo(session_factory)
    [r] = await recordatorios(session_factory, turno)
    assert (r.id, r.estado, r.enviado_en, r.updated_at) == (rid, "enviado", antes.enviado_en, antes.updated_at)


async def test_ciclos_repetidos_sobre_un_turno_sin_recordatorio_generan_uno_solo(session_factory: Factory) -> None:
    mundo = await _mundo(session_factory)
    turno = await insertar_turno(session_factory, mundo, AHORA + timedelta(hours=30))
    primero = await ciclo(session_factory)
    segundo = await ciclo(session_factory)
    assert (primero.generados, segundo.generados) == (1, 0)
    assert len(await recordatorios(session_factory, turno)) == 1


async def test_dos_workers_en_el_mismo_instante_dejan_un_solo_recordatorio_sin_error(session_factory: Factory) -> None:
    mundo = await _mundo(session_factory)
    turnos = [await insertar_turno(session_factory, mundo, AHORA + timedelta(hours=30 + i), sillon="s1")
              for i in range(3)]
    resultados = await asyncio.gather(*[ciclo(session_factory) for _ in range(4)], return_exceptions=True)
    assert not [r for r in resultados if isinstance(r, BaseException)], resultados
    for turno in turnos:
        assert len(await recordatorios(session_factory, turno)) == 1
    assert sum(r.generados for r in resultados if not isinstance(r, BaseException)) == 3
