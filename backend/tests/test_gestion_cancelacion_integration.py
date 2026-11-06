"""C-07 (3.1): GET/cancelar de /api/public/gestion con el código en la cabecera. Datos sintéticos (R19)."""

import logging
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.core import RegistroAuditoria
from app.pagos.service import cambiar_estado_turno
from app.turnos.models import Turno
from tests.sena_helpers import (
    TELEFONO, cabecera, fecha_laboral, iniciar, local, pagos_de, reservar, sembrar_agenda, turno_de,
)
from tests.test_sena_transiciones_integration import _reservado_con_sena

URL = "/api/public/gestion"
NO_ENCONTRADO = {"detail": "No encontramos un turno con ese código"}


async def _en_espera(client, ids, factory, hhmm="10:00"):
    f = fecha_laboral()
    await sembrar_agenda(factory, ids, f)
    reserva = await reservar(client, ids, local(f, hhmm))
    await iniciar(client, reserva, "mercadopago")
    return reserva, local(f, hhmm)


async def _turno_interno_sin_codigo(factory, ids) -> None:
    async with factory() as s:
        s.add(Turno(profesional_id=ids["profesional_id"], sillon_id=ids["sillon_id"],
                    tratamiento_id=ids["tratamiento_id"], paciente_id=None,
                    inicio=local(fecha_laboral(), "15:00"), fin=local(fecha_laboral(), "15:30"),
                    estado="reservado", codigo_gestion=None, contacto_nombre="Carlos Sintético",
                    contacto_telefono=TELEFONO))
        await s.commit()


async def _auditorias(factory, turno_id: int, origen: str):
    async with factory() as s:
        filas = (await s.execute(select(RegistroAuditoria).where(
            RegistroAuditoria.entidad == "turno", RegistroAuditoria.entidad_id == str(turno_id)))).scalars().all()
    return [f for f in filas if f.datos_despues.get("origen") == origen]


async def _slots(client, ids, dia) -> list[datetime]:
    d = await client.get("/api/public/disponibilidad", params={
        "profesional_id": ids["profesional_id"], "tratamiento_id": ids["tratamiento_id"],
        "desde": dia.isoformat(), "hasta": dia.isoformat()})
    return [datetime.fromisoformat(s["inicio"]) for s in d.json()["slots"]]


# --- Acceso por código ------------------------------------------------------------------------------------

@pytest.mark.parametrize("metodo,ruta,cuerpo", [
    ("GET", "", None), ("POST", "/cancelar", None),
    ("POST", "/reprogramar", {"inicio": "2031-01-01T10:00:00-03:00"})])
async def test_codigo_ausente_vacio_o_desconocido_es_el_mismo_404(
        client, seed_ids, session_factory, notificador, metodo, ruta, cuerpo) -> None:
    await _turno_interno_sin_codigo(session_factory, seed_ids)
    cabeceras = [{}, {"X-Codigo-Gestion": ""}, {"X-Codigo-Gestion": "no-existe-0000"},
                 {"X-Codigo-Gestion": "corto"}, {"X-Codigo-Gestion": "x" * 200}]
    for cab in cabeceras:
        r = await client.request(metodo, URL + ruta, headers=cab, json=cuerpo)
        assert r.status_code == 404 and r.json() == NO_ENCONTRADO, cab
    assert notificador.eventos == []


async def test_el_codigo_en_la_ruta_o_en_la_query_no_cuenta(client, seed_ids, session_factory, pasarela) -> None:
    reserva, _ = await _en_espera(client, seed_ids, session_factory)
    codigo = reserva["codigo_gestion"]
    assert (await client.get(f"{URL}/{codigo}")).status_code == 404
    assert (await client.get(URL, params={"codigo_gestion": codigo})).status_code == 404
    assert (await client.get(URL, headers=cabecera(reserva))).status_code == 200


# --- Consulta ----------------------------------------------------------------------------------------------

async def test_get_reservado_a_48h_permite_todo_y_no_filtra_el_telefono(
        client, seed_ids, session_factory, pasarela, reloj) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    reloj(inicio - timedelta(hours=48))
    r = await client.get(URL, headers=cabecera(reserva))
    assert r.status_code == 200
    j = r.json()
    assert j["estado"] == "reservado" and j["puede_cancelar"] is True and j["puede_reprogramar"] is True
    assert j["motivo_no_cancelable"] is None and j["motivo_no_reprogramable"] is None
    assert j["sena"] == {"monto": "3000.00", "estado": "acreditado"}
    assert j["limite_cambios"].endswith("-03:00")
    assert datetime.fromisoformat(j["limite_cambios"]) == inicio - timedelta(hours=24)
    assert j["inicio"].endswith("-03:00") and j["fin"].endswith("-03:00")
    assert j["tratamiento"] == {"id": seed_ids["tratamiento_id"], "nombre": "Limpieza", "duracion_minutos": 30}
    assert j["profesional"] == {"id": seed_ids["profesional_id"], "nombre": "Dra. Test"}
    assert j["texto_politica_reembolso"]
    assert TELEFONO not in r.text and "Carlos" not in r.text and "telefono" not in r.text


async def test_get_dentro_de_las_24h_bloquea_ambas_acciones_con_el_mismo_limite(
        client, seed_ids, session_factory, pasarela, reloj) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    reloj(inicio - timedelta(hours=23, minutes=59))
    j = (await client.get(URL, headers=cabecera(reserva))).json()
    assert j["puede_cancelar"] is False and j["puede_reprogramar"] is False
    assert j["motivo_no_cancelable"] == "fuera_de_plazo" and j["motivo_no_reprogramable"] == "fuera_de_plazo"
    assert datetime.fromisoformat(j["limite_cambios"]) == inicio - timedelta(hours=24)


async def test_get_de_un_cancelado_es_no_modificable(
        client, seed_ids, session_factory, pasarela, reloj) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    async with session_factory() as s:
        await cambiar_estado_turno(s, reserva["turno_id"], "cancelado", None, ahora=inicio - timedelta(hours=48))
    reloj(inicio - timedelta(hours=47))
    j = (await client.get(URL, headers=cabecera(reserva))).json()
    assert j["estado"] == "cancelado" and j["puede_cancelar"] is False and j["puede_reprogramar"] is False
    assert j["motivo_no_cancelable"] == "turno_no_modificable" == j["motivo_no_reprogramable"]


async def test_get_de_una_pre_reserva_se_puede_cancelar_pero_no_reprogramar(
        client, seed_ids, session_factory, pasarela, reloj) -> None:
    reserva, inicio = await _en_espera(client, seed_ids, session_factory)
    reloj(inicio - timedelta(hours=3))
    j = (await client.get(URL, headers=cabecera(reserva))).json()
    assert j["estado"] == "en_espera" and j["puede_cancelar"] is True and j["puede_reprogramar"] is False
    assert j["motivo_no_reprogramable"] == "sena_pendiente" and j["sena"]["estado"] == "pendiente"


# --- Cancelación -------------------------------------------------------------------------------------------

async def test_cancelar_reservado_a_48h_devuelve_la_sena_libera_el_horario_y_audita(
        client, seed_ids, session_factory, pasarela, reloj, notificador) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    reloj(inicio - timedelta(hours=48))
    r = await client.post(URL + "/cancelar", headers=cabecera(reserva))
    assert r.status_code == 200 and r.json() == {"estado": "cancelado", "estado_sena": "a_reembolsar"}
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "cancelado"
    assert (await pagos_de(session_factory, reserva["turno_id"]))[0].estado == "a_reembolsar"
    assert inicio in await _slots(client, seed_ids, inicio.date())
    assert len(await _auditorias(session_factory, reserva["turno_id"], "cancelacion_paciente")) == 1
    (ev,) = notificador.eventos
    assert ev.tipo == "turno_cancelado" and ev.turno_id == reserva["turno_id"]
    assert ev.inicio_anterior == inicio and ev.inicio_nuevo is None
    assert TELEFONO not in repr(ev) and "Carlos" not in repr(ev)


async def test_cancelar_confirmado_a_23h59_es_409_fuera_de_plazo_y_nada_cambia(
        client, seed_ids, session_factory, pasarela, reloj, notificador) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    async with session_factory() as s:
        await cambiar_estado_turno(s, reserva["turno_id"], "confirmado", None)
    reloj(inicio - timedelta(hours=23, minutes=59))
    r = await client.post(URL + "/cancelar", headers=cabecera(reserva))
    assert r.status_code == 409
    j = r.json()
    assert j["motivo"] == "fuera_de_plazo" and "clínica" in j["detail"]
    assert datetime.fromisoformat(j["limite_cambios"]) == inicio - timedelta(hours=24)
    assert j["limite_cambios"].endswith("-03:00")
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "confirmado"
    assert (await pagos_de(session_factory, reserva["turno_id"]))[0].estado == "acreditado"
    assert inicio not in await _slots(client, seed_ids, inicio.date())
    assert notificador.eventos == []


async def test_el_borde_exacto_de_24h_se_acepta_y_un_segundo_menos_se_rechaza(
        client, seed_ids, session_factory, pasarela, reloj) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    reloj(inicio - timedelta(hours=24) + timedelta(seconds=1))
    assert (await client.post(URL + "/cancelar", headers=cabecera(reserva))).status_code == 409
    reloj(inicio - timedelta(hours=24))
    r = await client.post(URL + "/cancelar", headers=cabecera(reserva))
    assert r.status_code == 200 and r.json()["estado_sena"] == "a_reembolsar"


async def test_cancelar_una_pre_reserva_a_3h_no_aplica_ventana_ni_toca_la_caja(
        client, seed_ids, session_factory, pasarela, reloj, notificador) -> None:
    reserva, inicio = await _en_espera(client, seed_ids, session_factory)
    reloj(inicio - timedelta(hours=3))
    r = await client.post(URL + "/cancelar", headers=cabecera(reserva))
    assert r.status_code == 200 and r.json() == {"estado": "cancelado", "estado_sena": "vencido"}
    assert [p.estado for p in await pagos_de(session_factory, reserva["turno_id"])] == ["vencido"]  # R8
    assert notificador.eventos == []  # un en_espera nunca tuvo evento de calendario


@pytest.mark.parametrize("final", ["cancelado", "ausente", "atendido"])
async def test_cancelar_un_turno_en_estado_final_es_409_no_modificable(
        client, seed_ids, session_factory, pasarela, reloj, notificador, final) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    ahora = inicio - timedelta(hours=48) if final == "cancelado" else inicio + timedelta(minutes=10)
    async with session_factory() as s:
        await cambiar_estado_turno(s, reserva["turno_id"], final, None, ahora=ahora)
    estado_pago = (await pagos_de(session_factory, reserva["turno_id"]))[0].estado
    reloj(inicio - timedelta(hours=72))
    r = await client.post(URL + "/cancelar", headers=cabecera(reserva))
    assert r.status_code == 409 and r.json()["motivo"] == "turno_no_modificable"
    assert (await pagos_de(session_factory, reserva["turno_id"]))[0].estado == estado_pago
    if final == "ausente":
        assert estado_pago == "no_reembolsado"  # R9
    assert notificador.eventos == []


async def test_si_el_publicador_falla_la_cancelacion_igual_es_200(
        client, seed_ids, session_factory, pasarela, reloj, notificador, caplog) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    notificador.falla = True
    reloj(inicio - timedelta(hours=48))
    with caplog.at_level(logging.ERROR):
        r = await client.post(URL + "/cancelar", headers=cabecera(reserva))
    assert r.status_code == 200
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "cancelado"
    assert TELEFONO not in caplog.text


async def test_cancelar_dos_veces_la_segunda_es_409(
        client, seed_ids, session_factory, pasarela, reloj) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    reloj(inicio - timedelta(hours=48))
    assert (await client.post(URL + "/cancelar", headers=cabecera(reserva))).status_code == 200
    r = await client.post(URL + "/cancelar", headers=cabecera(reserva))
    assert r.status_code == 409 and r.json()["motivo"] == "turno_no_modificable"
