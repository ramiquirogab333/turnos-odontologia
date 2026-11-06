"""C-07 (4.2): POST /api/public/gestion/reprogramar. Datos 100% sintéticos (R19)."""

import asyncio
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, update

from app.models.core import RegistroAuditoria
from app.pagos.service import cambiar_estado_turno
from app.turnos.models import Profesional, Tratamiento, Turno
from tests.sena_helpers import (
    TELEFONO, cabecera, configurar, fecha_laboral, iniciar, local, pagos_de, reservar, sembrar_agenda, turno_de,
)
from tests.test_sena_transiciones_integration import _reservado_con_sena

URL = "/api/public/gestion/reprogramar"


def _cuerpo(inicio: datetime) -> dict[str, str]:
    return {"inicio": inicio.isoformat()}


async def _insertar_turno(factory, ids, inicio, *, estado="reservado", profesional_id=None) -> dict[str, object]:
    codigo = str(uuid.uuid4())
    async with factory() as s:
        t = Turno(profesional_id=profesional_id or ids["profesional_id"], sillon_id=ids["sillon_id"],
                  tratamiento_id=ids["tratamiento_id"], paciente_id=None, inicio=inicio,
                  fin=inicio + timedelta(minutes=30), estado=estado, codigo_gestion=codigo,
                  contacto_nombre="Otra Sintética", contacto_telefono="+5491155556666")
        s.add(t)
        await s.flush()
        await s.commit()
        return {"turno_id": int(t.id), "codigo_gestion": codigo}


async def _auditorias(factory, turno_id: int):
    async with factory() as s:
        filas = (await s.execute(select(RegistroAuditoria).where(
            RegistroAuditoria.entidad == "turno", RegistroAuditoria.entidad_id == str(turno_id)))).scalars().all()
    return [f for f in filas if f.datos_despues.get("origen") == "reprogramacion_paciente"]


async def _slots(client, ids, dia) -> list[datetime]:
    d = await client.get("/api/public/disponibilidad", params={
        "profesional_id": ids["profesional_id"], "tratamiento_id": ids["tratamiento_id"],
        "desde": dia.isoformat(), "hasta": dia.isoformat()})
    return [datetime.fromisoformat(s["inicio"]) for s in d.json()["slots"]]


async def test_reprogramar_a_72h_conserva_id_codigo_y_sena_libera_el_horario_viejo(
        client, seed_ids, session_factory, pasarela, reloj, notificador) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    reloj(inicio - timedelta(hours=72))
    nuevo = local(inicio.date(), "11:00")
    r = await client.post(URL, json=_cuerpo(nuevo), headers=cabecera(reserva))
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["estado"] == "reservado" and j["estado_sena"] == "acreditado"
    assert datetime.fromisoformat(j["inicio"]) == nuevo and datetime.fromisoformat(j["fin"]) == nuevo + timedelta(minutes=30)
    assert j["inicio"].endswith("-03:00")
    turno = await turno_de(session_factory, reserva["turno_id"])
    assert turno.id == reserva["turno_id"] and turno.codigo_gestion == reserva["codigo_gestion"]
    assert (turno.inicio, turno.fin, turno.estado) == (nuevo, nuevo + timedelta(minutes=30), "reservado")
    (pago,) = await pagos_de(session_factory, reserva["turno_id"])  # el mismo pago, ningún otro activo
    assert pago.estado == "acreditado" and pago.monto == Decimal("3000.00")
    slots = await _slots(client, seed_ids, inicio.date())
    assert inicio in slots and nuevo not in slots
    (aud,) = await _auditorias(session_factory, reserva["turno_id"])
    assert datetime.fromisoformat(aud.datos_antes["inicio"]) == inicio
    assert datetime.fromisoformat(aud.datos_despues["inicio"]) == nuevo
    assert "Carlos" not in str(aud.datos_despues) and TELEFONO not in str(aud.datos_despues)
    (ev,) = notificador.eventos
    assert ev.tipo == "turno_reprogramado" and ev.inicio_anterior == inicio and ev.inicio_nuevo == nuevo
    assert ev.fin_nuevo == nuevo + timedelta(minutes=30)


async def test_un_confirmado_reprogramado_vuelve_a_reservado(
        client, seed_ids, session_factory, pasarela, reloj) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    async with session_factory() as s:
        await cambiar_estado_turno(s, reserva["turno_id"], "confirmado", None)
    reloj(inicio - timedelta(days=5))
    r = await client.post(URL, json=_cuerpo(local(inicio.date(), "12:00")), headers=cabecera(reserva))
    assert r.status_code == 200 and r.json()["estado"] == "reservado"
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "reservado"
    assert (await pagos_de(session_factory, reserva["turno_id"]))[0].estado == "acreditado"


async def test_con_23h59_es_fuera_de_plazo_y_nada_cambia(
        client, seed_ids, session_factory, pasarela, reloj, notificador) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    reloj(inicio - timedelta(hours=23, minutes=59))
    r = await client.post(URL, json=_cuerpo(local(inicio.date(), "11:00")), headers=cabecera(reserva))
    assert r.status_code == 409 and r.json()["motivo"] == "fuera_de_plazo"
    assert datetime.fromisoformat(r.json()["limite_cambios"]) == inicio - timedelta(hours=24)
    turno = await turno_de(session_factory, reserva["turno_id"])
    assert turno.inicio == inicio and (await pagos_de(session_factory, reserva["turno_id"]))[0].estado == "acreditado"
    assert notificador.eventos == []


async def test_exactamente_24h_y_un_horario_que_solo_se_superpone_con_el_propio_se_acepta(
        client, seed_ids, session_factory, pasarela, reloj) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    reloj(inicio - timedelta(hours=24))
    nuevo = local(inicio.date(), "10:15")  # 10:15-10:45 solo choca con el turno que se está moviendo
    r = await client.post(URL, json=_cuerpo(nuevo), headers=cabecera(reserva))
    assert r.status_code == 200, r.text
    assert (await turno_de(session_factory, reserva["turno_id"])).inicio == nuevo


async def test_horario_ocupado_por_la_misma_profesional_es_409_con_alternativas(
        client, seed_ids, session_factory, pasarela, reloj) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    await _insertar_turno(session_factory, seed_ids, local(inicio.date(), "11:00"))
    reloj(inicio - timedelta(hours=72))
    r = await client.post(URL, json=_cuerpo(local(inicio.date(), "11:00")), headers=cabecera(reserva))
    assert r.status_code == 409
    j = r.json()
    assert j["motivo"] == "profesional" and len(j["alternativas"]) > 0
    assert {"inicio", "fin", "sillon_id"} <= set(j["alternativas"][0])
    turno = await turno_de(session_factory, reserva["turno_id"])
    assert turno.inicio == inicio and (await pagos_de(session_factory, reserva["turno_id"]))[0].estado == "acreditado"


async def test_sin_sillon_libre_es_409_sillon(client, seed_ids, session_factory, pasarela, reloj) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    async with session_factory() as s:  # otra profesional ocupa el único sillón a las 11:00
        otra = Profesional(nombre="Dr. Otro Sintético", matricula="MAT-002", especialidad="General")
        s.add(otra)
        await s.flush()
        await s.commit()
        otra_id = int(otra.id)
    await _insertar_turno(session_factory, seed_ids, local(inicio.date(), "11:00"), profesional_id=otra_id)
    reloj(inicio - timedelta(hours=72))
    r = await client.post(URL, json=_cuerpo(local(inicio.date(), "11:00")), headers=cabecera(reserva))
    assert r.status_code == 409 and r.json()["motivo"] == "sillon"
    assert (await turno_de(session_factory, reserva["turno_id"])).inicio == inicio


@pytest.mark.parametrize("hhmm", ["16:45", "20:00", "08:30"])
async def test_fuera_de_la_franja_es_422_y_el_turno_no_cambia(
        client, seed_ids, session_factory, pasarela, reloj, hhmm) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)  # franja 09:00-17:00, 30 min
    reloj(inicio - timedelta(hours=72))
    r = await client.post(URL, json=_cuerpo(local(inicio.date(), hhmm)), headers=cabecera(reserva))
    assert r.status_code == 422 and r.json()["motivo"] == "fuera_de_disponibilidad"
    assert (await turno_de(session_factory, reserva["turno_id"])).inicio == inicio


async def test_el_ultimo_slot_que_entra_justo_en_la_franja_se_acepta(
        client, seed_ids, session_factory, pasarela, reloj) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    reloj(inicio - timedelta(hours=72))
    r = await client.post(URL, json=_cuerpo(local(inicio.date(), "16:30")), headers=cabecera(reserva))
    assert r.status_code == 200 and (await turno_de(session_factory, reserva["turno_id"])).fin == local(inicio.date(), "17:00")


async def test_mismo_horario_pasado_o_sin_zona_es_422(
        client, seed_ids, session_factory, pasarela, reloj) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    ahora = inicio - timedelta(hours=72)
    reloj(ahora)
    mismo = await client.post(URL, json=_cuerpo(inicio), headers=cabecera(reserva))
    assert mismo.status_code == 422 and mismo.json()["motivo"] == "mismo_horario"
    pasado = await client.post(URL, json=_cuerpo(ahora - timedelta(hours=1)), headers=cabecera(reserva))
    assert pasado.status_code == 422 and pasado.json()["motivo"] == "horario_pasado"
    sin_zona = await client.post(URL, json={"inicio": "2031-11-18T11:00:00"}, headers=cabecera(reserva))
    assert sin_zona.status_code == 422
    assert (await turno_de(session_factory, reserva["turno_id"])).inicio == inicio


async def test_una_pre_reserva_en_espera_no_se_reprograma(
        client, seed_ids, session_factory, pasarela, reloj, notificador) -> None:
    f = fecha_laboral()
    await sembrar_agenda(session_factory, seed_ids, f)
    reserva = await reservar(client, seed_ids, local(f, "10:00"))
    await iniciar(client, reserva, "mercadopago")
    reloj(local(f, "10:00") - timedelta(days=2))
    r = await client.post(URL, json=_cuerpo(local(f, "11:00")), headers=cabecera(reserva))
    assert r.status_code == 409 and r.json()["motivo"] == "sena_pendiente"
    assert "Cancelalo y reservá otro horario" in r.json()["detail"]
    assert (await turno_de(session_factory, reserva["turno_id"])).inicio == local(f, "10:00")
    assert notificador.eventos == []


@pytest.mark.parametrize("final", ["atendido", "ausente", "cancelado"])
async def test_un_turno_en_estado_final_no_se_reprograma_y_la_sena_queda_igual(
        client, seed_ids, session_factory, pasarela, reloj, final) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    ahora = inicio - timedelta(hours=48) if final == "cancelado" else inicio + timedelta(minutes=10)
    async with session_factory() as s:
        await cambiar_estado_turno(s, reserva["turno_id"], final, None, ahora=ahora)
    antes = (await pagos_de(session_factory, reserva["turno_id"]))[0].estado
    reloj(inicio - timedelta(hours=72))
    r = await client.post(URL, json=_cuerpo(local(inicio.date(), "11:00")), headers=cabecera(reserva))
    assert r.status_code == 409 and r.json()["motivo"] == "turno_no_modificable"
    assert (await pagos_de(session_factory, reserva["turno_id"]))[0].estado == antes
    if final == "ausente":
        assert antes == "no_reembolsado"  # R9
    assert (await turno_de(session_factory, reserva["turno_id"])).inicio == inicio


async def test_cambiar_el_porcentaje_y_el_precio_despues_de_acreditar_no_toca_la_sena(
        client, seed_ids, session_factory, pasarela, reloj) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    await configurar(session_factory, sena_porcentaje=Decimal("50.00"))
    async with session_factory() as s:
        await s.execute(update(Tratamiento).where(Tratamiento.id == seed_ids["tratamiento_id"])
                        .values(precio_base=Decimal("20000.00")))
        await s.commit()
    reloj(inicio - timedelta(hours=72))
    r = await client.post(URL, json=_cuerpo(local(inicio.date(), "13:00")), headers=cabecera(reserva))
    assert r.status_code == 200
    (pago,) = await pagos_de(session_factory, reserva["turno_id"])
    assert pago.monto == Decimal("3000.00") and pago.estado == "acreditado"


async def test_dos_reprogramaciones_concurrentes_al_mismo_horario_una_gana_y_la_otra_recibe_409(
        client, seed_ids, session_factory, pasarela, reloj) -> None:
    f = fecha_laboral()
    await sembrar_agenda(session_factory, seed_ids, f)
    a = await _insertar_turno(session_factory, seed_ids, local(f, "10:00"))
    b = await _insertar_turno(session_factory, seed_ids, local(f, "10:30"))
    reloj(local(f, "10:00") - timedelta(hours=72))
    destino = _cuerpo(local(f, "14:00"))
    ra, rb = await asyncio.gather(
        client.post(URL, json=destino, headers=cabecera(a)), client.post(URL, json=destino, headers=cabecera(b)))
    assert sorted([ra.status_code, rb.status_code]) == [200, 409]
    perdedora = ra if ra.status_code == 409 else rb
    assert perdedora.json()["motivo"] == "profesional" and len(perdedora.json()["alternativas"]) > 0
    quedaron = {(await turno_de(session_factory, t["turno_id"])).inicio for t in (a, b)}
    assert local(f, "14:00") in quedaron and len(quedaron) == 2  # nadie perdió su horario original


async def test_la_base_es_la_red_de_seguridad_si_se_saltea_el_prechequeo_nunca_500(
        client, seed_ids, session_factory, pasarela, reloj, monkeypatch) -> None:
    reserva, inicio = await _reservado_con_sena(client, seed_ids, session_factory)
    await _insertar_turno(session_factory, seed_ids, local(inicio.date(), "11:00"))

    async def sin_bloqueos(*args, **kwargs):  # type: ignore[no-untyped-def]
        return []

    monkeypatch.setattr("app.gestion.service._cargar_bloqueos", sin_bloqueos)
    reloj(inicio - timedelta(hours=72))
    r = await client.post(URL, json=_cuerpo(local(inicio.date(), "11:00")), headers=cabecera(reserva))
    assert r.status_code == 409 and r.json()["motivo"] in ("profesional", "sillon")  # 23P01 del EXCLUDE (R5)
    assert (await turno_de(session_factory, reserva["turno_id"])).inicio == inicio
