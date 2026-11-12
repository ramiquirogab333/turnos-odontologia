"""C-09 (7.1-7.4, D5): POST /api/public/gestion/confirmar y ``puede_confirmar`` de la consulta. Sintético (R19)."""

import logging
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models.core import RegistroAuditoria
from app.pagos.service import cambiar_estado_turno
from tests.recordatorios_helpers import ciclo, recordatorios, sembrar_recordatorio
from tests.sena_helpers import cabecera, fecha_laboral, iniciar, local, reservar, sembrar_agenda, turno_de
from tests.test_sena_transiciones_integration import _reservado_con_sena

URL = "/api/public/gestion"
NO_ENCONTRADO = {"detail": "No encontramos un turno con ese código"}


async def _auditorias(factory, turno_id: int):
    async with factory() as s:
        filas = (await s.execute(select(RegistroAuditoria).where(
            RegistroAuditoria.entidad == "turno", RegistroAuditoria.entidad_id == str(turno_id)))).scalars().all()
    return [f for f in filas if f.datos_despues.get("origen") == "confirmacion_paciente"]


async def _en_espera(client, ids, factory):
    f = fecha_laboral()
    await sembrar_agenda(factory, ids, f)
    reserva = await reservar(client, ids, local(f, "10:00"))
    await iniciar(client, reserva, "mercadopago")
    return reserva, local(f, "10:00")


# --- 7.1 Confirmación -------------------------------------------------------------------------------------------

async def test_el_paciente_confirma_su_turno_reservado_y_queda_auditado(
        client, seed_ids, session_factory, pasarela, reloj) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    reloj(inicio - timedelta(hours=30))
    r = await client.post(URL + "/confirmar", headers=cabecera(reserva))
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["estado"] == "confirmado" and j["inicio"].endswith("-03:00")
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "confirmado"
    (aud,) = await _auditorias(session_factory, reserva["turno_id"])
    assert aud.datos_antes["estado"] == "reservado" and aud.usuario_id is None
    assert "Carlos" not in str(aud.datos_despues)


@pytest.mark.parametrize("cabeceras", [{}, {"X-Codigo-Gestion": ""}, {"X-Codigo-Gestion": "no-existe-0000"},
                                       {"X-Codigo-Gestion": "corto"}])
async def test_un_codigo_ausente_o_desconocido_es_el_404_generico_y_ningun_turno_cambia(
        client, seed_ids, session_factory, pasarela, reloj, cabeceras) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    reloj(inicio - timedelta(hours=30))
    r = await client.post(URL + "/confirmar", headers=cabeceras)
    assert r.status_code == 404 and r.json() == NO_ENCONTRADO
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "reservado"


async def test_se_puede_confirmar_con_menos_de_24_horas(client, seed_ids, session_factory, pasarela, reloj) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    reloj(inicio - timedelta(hours=2))
    r = await client.post(URL + "/confirmar", headers=cabecera(reserva))
    assert r.status_code == 200 and r.json()["estado"] == "confirmado"


async def test_confirmar_no_publica_eventos_de_calendario(
        client, seed_ids, session_factory, pasarela, reloj, notificador) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    reloj(inicio - timedelta(hours=30))
    assert (await client.post(URL + "/confirmar", headers=cabecera(reserva))).status_code == 200
    assert notificador.eventos == []


# --- Rechazos ---------------------------------------------------------------------------------------------------

async def test_confirmar_dos_veces_es_200_y_no_agrega_otra_auditoria(
        client, seed_ids, session_factory, pasarela, reloj) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    reloj(inicio - timedelta(hours=30))
    primera = await client.post(URL + "/confirmar", headers=cabecera(reserva))
    segunda = await client.post(URL + "/confirmar", headers=cabecera(reserva))
    assert (primera.status_code, segunda.status_code) == (200, 200) and segunda.json()["estado"] == "confirmado"
    assert len(await _auditorias(session_factory, reserva["turno_id"])) == 1


async def test_una_pre_reserva_en_espera_es_409_sena_pendiente_y_sigue_en_espera(
        client, seed_ids, session_factory, pasarela, reloj) -> None:
    reserva, inicio = await _en_espera(client, seed_ids, session_factory)
    reloj(inicio - timedelta(hours=30))
    r = await client.post(URL + "/confirmar", headers=cabecera(reserva))
    assert r.status_code == 409 and r.json()["motivo"] == "sena_pendiente"
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "en_espera"
    assert await _auditorias(session_factory, reserva["turno_id"]) == []


@pytest.mark.parametrize("estado", ["cancelado", "ausente", "atendido"])
async def test_un_turno_en_estado_final_es_409_turno_no_modificable(
        client, seed_ids, session_factory, pasarela, reloj, estado) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    async with session_factory() as s:
        await cambiar_estado_turno(s, reserva["turno_id"], estado, None, ahora=inicio + timedelta(minutes=15)
                                   if estado != "cancelado" else inicio - timedelta(days=3))
    reloj(inicio - timedelta(hours=30))
    r = await client.post(URL + "/confirmar", headers=cabecera(reserva))
    assert r.status_code == 409 and r.json()["motivo"] == "turno_no_modificable"
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == estado


async def test_en_el_instante_exacto_del_inicio_es_409_turno_iniciado(
        client, seed_ids, session_factory, pasarela, reloj) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    reloj(inicio)
    r = await client.post(URL + "/confirmar", headers=cabecera(reserva))
    assert r.status_code == 409 and r.json()["motivo"] == "turno_iniciado"
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "reservado"
    reloj(inicio - timedelta(seconds=1))  # un segundo antes todavía se puede
    assert (await client.post(URL + "/confirmar", headers=cabecera(reserva))).status_code == 200


async def test_el_codigo_no_aparece_en_los_logs(
        client, seed_ids, session_factory, pasarela, reloj, caplog: pytest.LogCaptureFixture) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    reloj(inicio - timedelta(hours=30))
    with caplog.at_level(logging.DEBUG):
        await client.post(URL + "/confirmar", headers=cabecera(reserva))
    assert reserva["codigo_gestion"] not in caplog.text


# --- 7.3 El recordatorio se cierra ------------------------------------------------------------------------------

async def test_confirmar_cierra_el_recordatorio_enviado_con_la_fecha(
        client, seed_ids, session_factory, pasarela, reloj) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    await sembrar_recordatorio(session_factory, reserva["turno_id"], inicio, "enviado")
    ahora = inicio - timedelta(hours=30)
    reloj(ahora)
    assert (await client.post(URL + "/confirmar", headers=cabecera(reserva))).status_code == 200
    [r] = await recordatorios(session_factory, reserva["turno_id"])
    assert (r.estado, r.confirmado_en) == ("confirmado", ahora)


async def test_confirmar_un_turno_cancelado_es_409_y_su_recordatorio_sigue_anulado(
        client, seed_ids, session_factory, pasarela, reloj) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    async with session_factory() as s:
        await cambiar_estado_turno(s, reserva["turno_id"], "cancelado", None, ahora=inicio - timedelta(days=3))
    await sembrar_recordatorio(session_factory, reserva["turno_id"], inicio, "anulado", motivo="turno_cancelado")
    reloj(inicio - timedelta(hours=30))
    assert (await client.post(URL + "/confirmar", headers=cabecera(reserva))).status_code == 409
    [r] = await recordatorios(session_factory, reserva["turno_id"])
    assert r.estado == "anulado"


async def test_confirmar_antes_del_recordatorio_y_luego_entrar_en_la_anticipacion_no_genera_ninguno(
        client, seed_ids, session_factory, pasarela, reloj) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    reloj(inicio - timedelta(days=5))
    assert (await client.post(URL + "/confirmar", headers=cabecera(reserva))).status_code == 200
    assert await recordatorios(session_factory, reserva["turno_id"]) == []
    await ciclo(session_factory, ahora=inicio - timedelta(hours=30))
    assert await recordatorios(session_factory, reserva["turno_id"]) == []
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "confirmado"


async def test_el_ciclo_cierra_el_recordatorio_de_un_turno_confirmado_si_la_marca_inmediata_fallo(
        client, seed_ids, session_factory, pasarela) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    await sembrar_recordatorio(session_factory, reserva["turno_id"], inicio, "enviado")
    async with session_factory() as s:
        await cambiar_estado_turno(s, reserva["turno_id"], "confirmado", None)  # sin pasar por la API
    await ciclo(session_factory, ahora=inicio - timedelta(hours=30))
    [r] = await recordatorios(session_factory, reserva["turno_id"])
    assert r.estado == "confirmado" and r.confirmado_en is not None


# --- 7.4 puede_confirmar ----------------------------------------------------------------------------------------

async def test_la_consulta_de_un_reservado_puede_confirmar(
        client, seed_ids, session_factory, pasarela, reloj) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    reloj(inicio - timedelta(hours=30))
    j = (await client.get(URL, headers=cabecera(reserva))).json()
    assert j["puede_confirmar"] is True and j["motivo_no_confirmable"] is None
    assert j["puede_cancelar"] is True  # los demás campos no cambian


async def test_la_consulta_de_un_cancelado_no_puede_confirmar(
        client, seed_ids, session_factory, pasarela, reloj) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    async with session_factory() as s:
        await cambiar_estado_turno(s, reserva["turno_id"], "cancelado", None, ahora=inicio - timedelta(days=3))
    reloj(inicio - timedelta(hours=30))
    j = (await client.get(URL, headers=cabecera(reserva))).json()
    assert (j["puede_confirmar"], j["motivo_no_confirmable"]) == (False, "turno_no_modificable")


async def test_la_consulta_de_un_confirmado_dice_ya_confirmado_y_conserva_la_ventana_de_cancelacion(
        client, seed_ids, session_factory, pasarela, reloj) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    async with session_factory() as s:
        await cambiar_estado_turno(s, reserva["turno_id"], "confirmado", None)
    reloj(inicio - timedelta(hours=30))
    j = (await client.get(URL, headers=cabecera(reserva))).json()
    assert (j["puede_confirmar"], j["motivo_no_confirmable"], j["puede_cancelar"]) == (False, "ya_confirmado", True)
    reloj(inicio - timedelta(hours=10))
    j = (await client.get(URL, headers=cabecera(reserva))).json()
    assert (j["puede_confirmar"], j["motivo_no_confirmable"], j["puede_cancelar"]) == (False, "ya_confirmado", False)


async def test_la_consulta_de_una_pre_reserva_no_puede_confirmar_por_sena_pendiente(
        client, seed_ids, session_factory, pasarela, reloj) -> None:
    reserva, inicio = await _en_espera(client, seed_ids, session_factory)
    reloj(inicio - timedelta(hours=30))
    j = (await client.get(URL, headers=cabecera(reserva))).json()
    assert (j["puede_confirmar"], j["motivo_no_confirmable"]) == (False, "sena_pendiente")


async def test_la_consulta_de_un_turno_que_empieza_ahora_no_puede_confirmar(
        client, seed_ids, session_factory, pasarela, reloj) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    reloj(inicio)
    j = (await client.get(URL, headers=cabecera(reserva))).json()
    assert (j["puede_confirmar"], j["motivo_no_confirmable"]) == (False, "turno_iniciado")
