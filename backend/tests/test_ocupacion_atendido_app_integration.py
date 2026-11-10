"""C-08 (1.8, O19): un ``atendido`` ocupa el horario hasta su ``fin`` en todos los caminos de la aplicación.

Datos 100 % sintéticos (R19). El estado se siembra por ORM: es el que deja recepción al marcar el turno antes de su hora.
"""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.pagos.service import acreditar_pago
from app.turnos.models import Turno
from tests.sena_helpers import (
    fecha_laboral, iniciar, local, pagos_de, reservar, sembrar_agenda, turno_de,
)

RESERVA_URL = "/api/public/turnos"


async def _sembrar_turno(factory, ids, inicio: datetime, estado: str, minutos: int = 30) -> int:
    async with factory() as s:
        t = Turno(profesional_id=ids["profesional_id"], sillon_id=ids["sillon_id"],
                  tratamiento_id=ids["tratamiento_id"], inicio=inicio, fin=inicio + timedelta(minutes=minutos),
                  estado=estado, codigo_gestion=str(uuid.uuid4()), contacto_nombre="Otra Sintética",
                  contacto_telefono="+5491155556666")
        s.add(t)
        await s.flush()
        await s.commit()
        return int(t.id)


async def _slots(client, ids, dia) -> list[datetime]:
    d = await client.get("/api/public/disponibilidad", params={
        "profesional_id": ids["profesional_id"], "tratamiento_id": ids["tratamiento_id"],
        "desde": dia.isoformat(), "hasta": dia.isoformat()})
    return [datetime.fromisoformat(s["inicio"]) for s in d.json()["slots"]]


def _cuerpo_reserva(ids, inicio: datetime) -> dict[str, object]:
    return {"nombre": "Carlos Sintético", "telefono": "+5491144445555", "tratamiento_id": ids["tratamiento_id"],
            "profesional_id": ids["profesional_id"], "inicio": inicio.isoformat()}


@pytest.fixture
async def agenda(seed_ids, session_factory):
    f = fecha_laboral()
    await sembrar_agenda(session_factory, seed_ids, f)
    return f


async def test_un_atendido_no_figura_en_la_disponibilidad_publica(client, seed_ids, session_factory, agenda) -> None:
    await _sembrar_turno(session_factory, seed_ids, local(agenda, "10:00"), "atendido")
    horarios = await _slots(client, seed_ids, agenda)
    assert local(agenda, "10:00") not in horarios
    assert local(agenda, "09:30") in horarios and local(agenda, "10:30") in horarios  # solo ese horario


async def test_un_ausente_libera_el_horario_en_la_disponibilidad(client, seed_ids, session_factory, agenda) -> None:
    await _sembrar_turno(session_factory, seed_ids, local(agenda, "10:00"), "ausente")
    assert local(agenda, "10:00") in await _slots(client, seed_ids, agenda)


async def test_la_reserva_publica_sobre_un_atendido_es_409_con_alternativas_y_sobre_un_ausente_es_201(
        client, seed_ids, session_factory, agenda) -> None:
    await _sembrar_turno(session_factory, seed_ids, local(agenda, "10:00"), "atendido")
    r = await client.post(RESERVA_URL, json=_cuerpo_reserva(seed_ids, local(agenda, "10:00")))
    assert r.status_code == 409, r.text
    assert r.json()["motivo"] == "profesional" and r.json()["alternativas"]
    otro = await _sembrar_turno(session_factory, seed_ids, local(agenda, "14:00"), "ausente")
    assert otro
    libre = await client.post(RESERVA_URL, json=_cuerpo_reserva(seed_ids, local(agenda, "14:00")))
    assert libre.status_code == 201, libre.text


async def test_un_turno_que_empieza_en_el_fin_del_atendido_se_acepta(client, seed_ids, session_factory, agenda) -> None:
    await _sembrar_turno(session_factory, seed_ids, local(agenda, "10:00"), "atendido")
    pegado = await client.post(RESERVA_URL, json=_cuerpo_reserva(seed_ids, local(agenda, "10:30")))
    assert pegado.status_code == 201, pegado.text


async def test_el_alta_interna_sobre_un_atendido_es_409_sobre_un_ausente_es_201(
        client, seed_ids, session_factory, agenda, token_recepcion) -> None:
    await _sembrar_turno(session_factory, seed_ids, local(agenda, "10:00"), "atendido")
    await _sembrar_turno(session_factory, seed_ids, local(agenda, "14:00"), "ausente")
    base = {"profesional_id": seed_ids["profesional_id"], "sillon_id": seed_ids["sillon_id"],
            "tratamiento_id": seed_ids["tratamiento_id"]}
    cabecera = {"Authorization": f"Bearer {token_recepcion}"}
    choca = await client.post("/api/turnos", json={**base, "inicio": local(agenda, "10:15").isoformat()},
                              headers=cabecera)
    assert choca.status_code == 409 and choca.json()["motivo"] == "profesional"
    libre = await client.post("/api/turnos", json={**base, "inicio": local(agenda, "14:15").isoformat()},
                              headers=cabecera)
    assert libre.status_code == 201, libre.text


async def test_reprogramar_a_un_horario_con_un_atendido_es_409_con_alternativas(
        client, seed_ids, session_factory, agenda, reloj, notificador) -> None:
    await _sembrar_turno(session_factory, seed_ids, local(agenda, "10:00"), "atendido")
    movil = await _sembrar_turno(session_factory, seed_ids, local(agenda, "15:00"), "reservado")
    reloj(local(agenda, "15:00") - timedelta(hours=72))
    async with session_factory() as s:
        codigo = (await s.execute(select(Turno.codigo_gestion).where(Turno.id == movil))).scalar_one()
    r = await client.post("/api/public/gestion/reprogramar", json={"inicio": local(agenda, "10:00").isoformat()},
                          headers={"X-Codigo-Gestion": str(codigo)})
    assert r.status_code == 409, r.text
    assert r.json()["motivo"] == "profesional" and r.json()["alternativas"]
    assert (await turno_de(session_factory, movil)).inicio == local(agenda, "15:00")


async def test_iniciar_la_sena_de_una_prereserva_superpuesta_a_un_atendido_es_409_sin_pago(
        client, seed_ids, session_factory, agenda, pasarela) -> None:
    reserva = await reservar(client, seed_ids, local(agenda, "10:00"))
    await _sembrar_turno(session_factory, seed_ids, local(agenda, "10:00"), "atendido")
    r = await iniciar(client, reserva, "mercadopago")
    assert r.status_code == 409, r.text
    assert r.json()["motivo"] == "profesional" and r.json()["alternativas"]
    assert await pagos_de(session_factory, reserva["turno_id"]) == []


async def test_acreditar_el_pago_de_una_prereserva_cuyo_horario_tomo_un_atendido_queda_a_reembolsar(
        client, seed_ids, session_factory, agenda, pasarela) -> None:
    reserva = await reservar(client, seed_ids, local(agenda, "10:00"))
    pago_id = (await iniciar(client, reserva, "mercadopago")).json()["pago_id"]
    await _sembrar_turno(session_factory, seed_ids, local(agenda, "10:00"), "atendido")
    async with session_factory() as s:
        r = await acreditar_pago(s, pago_id, mp_payment_id="PAY-ATENDIDO", monto_reportado=Decimal("3000.00"),
                                 moneda_reportada="ARS")
    assert r.efecto == "a_reembolsar"
    (pago,) = await pagos_de(session_factory, reserva["turno_id"])
    assert pago.estado == "a_reembolsar"
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "cancelado"
    async with session_factory() as s:
        atendidos = (await s.execute(select(func.count()).select_from(Turno).where(Turno.estado == "atendido"))).scalar_one()
    assert atendidos == 1
