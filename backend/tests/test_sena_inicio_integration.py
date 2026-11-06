"""C-06 (5.1): inicio y consulta de la seña (POST/GET /api/public/turnos/{id}/sena). PostgreSQL real, sin red."""

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select, update

from app.pagos.models import PagoSena
from app.turnos.models import Turno
from tests.sena_helpers import (
    ALIAS, CBU, cabecera, configurar, configurar_transferencia, fecha_laboral, forzar_vencimiento,
    iniciar, local, pagos_de, reservar, sembrar_agenda, turno_de,
)


async def _contexto(client, ids, session_factory, hhmm="10:00", precio="10000.00"):
    f = fecha_laboral()
    await sembrar_agenda(session_factory, ids, f, precio)
    await configurar_transferencia(session_factory)
    return f, await reservar(client, ids, local(f, hhmm))


async def test_mercadopago_201_con_checkout_url_y_un_unico_pago_pendiente(
        client, seed_ids, session_factory, pasarela) -> None:
    f, reserva = await _contexto(client, seed_ids, session_factory)
    r = await iniciar(client, reserva, "mercadopago")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["estado"] == "pendiente" and body["medio"] == "mercadopago"
    assert body["monto"] == "3000.00"
    assert body["checkout_url"] == f"http://localhost:5173/?pago=retorno&turno={reserva['turno_id']}"
    assert body["referencia_externa"] and "te devolvemos la seña" in body["texto_politica_reembolso"]
    assert datetime.fromisoformat(body["vence_en"]) <= local(f, "10:00")
    pagos = await pagos_de(session_factory, reserva["turno_id"])
    assert len(pagos) == 1 and pagos[0].estado == "pendiente" and pagos[0].monto == Decimal("3000.00")
    assert pagos[0].porcentaje_aplicado == Decimal("30.00") and pagos[0].checkout_url == body["checkout_url"]
    assert len(pasarela.preferencias) == 1 and pasarela.preferencias[0]["monto"] == Decimal("3000.00")


async def test_monto_con_redondeo_half_up_en_el_borde_del_centavo(client, seed_ids, session_factory, pasarela) -> None:
    _, reserva = await _contexto(client, seed_ids, session_factory, precio="3333.33")
    r = await iniciar(client, reserva, "mercadopago")
    assert r.status_code == 201 and r.json()["monto"] == "1000.00"


async def test_reintento_con_el_mismo_medio_es_200_con_la_misma_referencia(
        client, seed_ids, session_factory, pasarela) -> None:
    _, reserva = await _contexto(client, seed_ids, session_factory)
    primero = await iniciar(client, reserva, "mercadopago")
    segundo = await iniciar(client, reserva, "mercadopago")
    assert (primero.status_code, segundo.status_code) == (201, 200)
    assert segundo.json()["referencia_externa"] == primero.json()["referencia_externa"]
    assert segundo.json()["checkout_url"] == primero.json()["checkout_url"]
    assert len(pasarela.preferencias) == 1 and len(await pagos_de(session_factory, reserva["turno_id"])) == 1


async def test_cambio_a_transferencia_vence_el_pago_anterior_y_devuelve_los_datos_bancarios(
        client, seed_ids, session_factory, pasarela) -> None:
    f, reserva = await _contexto(client, seed_ids, session_factory)
    await iniciar(client, reserva, "mercadopago")
    r = await iniciar(client, reserva, "transferencia")
    assert r.status_code == 201, r.text
    body = r.json()
    assert (body["alias"], body["cbu"]) == (ALIAS, CBU) and body["titular"]
    concepto = body["referencia_concepto"]
    assert re.fullmatch(rf"SENA-{reserva['turno_id']}-[0-9A-F]{{6}}", concepto) and len(concepto) <= 20
    assert body["checkout_url"] is None and body["monto"] == "3000.00"
    pagos = await pagos_de(session_factory, reserva["turno_id"])
    assert [(p.medio, p.estado) for p in pagos] == [("mercadopago", "vencido"), ("transferencia", "pendiente")]
    # RN-SN-07: la transferencia extiende el vencimiento (24 h), siempre hasta el inicio como máximo
    vence = datetime.fromisoformat(body["vence_en"])
    esperado = min(datetime.now(timezone.utc) + timedelta(hours=24), local(f, "10:00"))
    assert abs((vence - esperado).total_seconds()) < 60
    assert (await turno_de(session_factory, reserva["turno_id"])).en_espera_vence_en == vence


async def test_cambio_de_transferencia_a_mercadopago_acota_el_vencimiento_a_30_minutos(
        client, seed_ids, session_factory, pasarela) -> None:
    _, reserva = await _contexto(client, seed_ids, session_factory)
    await iniciar(client, reserva, "transferencia")
    r = await iniciar(client, reserva, "mercadopago")
    assert r.status_code == 201
    vence = datetime.fromisoformat(r.json()["vence_en"])
    assert vence <= datetime.now(timezone.utc) + timedelta(minutes=31)


async def test_medio_deshabilitado_o_efectivo_es_422_y_no_crea_pago(client, seed_ids, session_factory, pasarela) -> None:
    _, reserva = await _contexto(client, seed_ids, session_factory)
    await configurar(session_factory, medios_habilitados=["mercadopago"])
    r = await iniciar(client, reserva, "transferencia")
    assert r.status_code == 422 and "mercadopago" in r.text
    assert (await iniciar(client, reserva, "efectivo")).status_code == 422
    assert await pagos_de(session_factory, reserva["turno_id"]) == []


async def test_transferencia_sin_alias_ni_cbu_cargados_es_422(client, seed_ids, session_factory, pasarela) -> None:
    f = fecha_laboral()
    await sembrar_agenda(session_factory, seed_ids, f)
    reserva = await reservar(client, seed_ids, local(f, "10:00"))
    assert reserva["sena"]["medios_habilitados"] == ["mercadopago"]  # sin datos bancarios no se ofrece
    assert (await iniciar(client, reserva, "transferencia")).status_code == 422


async def test_codigo_ausente_o_ajeno_es_404_sin_datos_de_contacto(client, seed_ids, session_factory, pasarela) -> None:
    f, reserva = await _contexto(client, seed_ids, session_factory)
    otra = await reservar(client, seed_ids, local(f, "11:00"), nombre="María Sintética")
    url = f"/api/public/turnos/{reserva['turno_id']}/sena"
    for cab in ({}, {"X-Codigo-Gestion": otra["codigo_gestion"]}, {"X-Codigo-Gestion": "x" * 36}):
        for r in (await client.post(url, json={"medio": "mercadopago"}, headers=cab), await client.get(url, headers=cab)):
            assert r.status_code == 404
            assert "Carlos" not in r.text and "+549" not in r.text
    assert (await client.get("/api/public/turnos/999999/sena", headers=cabecera(reserva))).status_code == 404
    assert await pagos_de(session_factory, reserva["turno_id"]) == []


async def test_turno_no_en_espera_o_vencido_es_409_estado_invalido(client, seed_ids, session_factory, pasarela) -> None:
    f, reserva = await _contexto(client, seed_ids, session_factory)
    vencido = await reservar(client, seed_ids, local(f, "12:00"))
    await forzar_vencimiento(session_factory, vencido["turno_id"], datetime.now(timezone.utc) - timedelta(seconds=1))
    r = await iniciar(client, vencido, "mercadopago")  # vencido por reloj aunque el barrido no corrió
    assert r.status_code == 409 and r.json()["motivo"] == "estado_invalido"
    async with session_factory() as s:
        await s.execute(update(Turno).where(Turno.id == reserva["turno_id"])
                        .values(estado="cancelado", en_espera_vence_en=None))
        await s.commit()
    r = await iniciar(client, reserva, "mercadopago")
    assert r.status_code == 409 and r.json()["motivo"] == "estado_invalido"
    async with session_factory() as s:
        assert (await s.execute(select(func.count()).select_from(PagoSena))).scalar_one() == 0


async def test_horario_ya_tomado_por_un_reservado_es_409_con_alternativas_y_sin_pago(
        client, seed_ids, session_factory, pasarela) -> None:
    f, reserva = await _contexto(client, seed_ids, session_factory)
    async with session_factory() as s:
        s.add(Turno(profesional_id=seed_ids["profesional_id"], sillon_id=seed_ids["sillon_id"],
                    tratamiento_id=seed_ids["tratamiento_id"], inicio=local(f, "10:00"),
                    fin=local(f, "10:30"), estado="reservado"))
        await s.commit()
    r = await iniciar(client, reserva, "mercadopago")
    assert r.status_code == 409, r.text
    assert r.json()["motivo"] == "profesional" and r.json()["alternativas"]
    assert await pagos_de(session_factory, reserva["turno_id"]) == []
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "en_espera"
    assert pasarela.preferencias == []


async def test_pasarela_caida_es_502_y_no_deja_pago_persistido(client, seed_ids, session_factory, pasarela) -> None:
    _, reserva = await _contexto(client, seed_ids, session_factory)
    pasarela.falla_crear = True
    r = await iniciar(client, reserva, "mercadopago")
    assert r.status_code == 502, r.text
    assert await pagos_de(session_factory, reserva["turno_id"]) == []
    pasarela.falla_crear = False
    assert (await iniciar(client, reserva, "mercadopago")).status_code == 201  # se puede reintentar


async def test_el_porcentaje_cambia_despues_de_iniciar_y_la_sena_conserva_monto_y_porcentaje(
        client, seed_ids, session_factory, pasarela) -> None:
    f, reserva = await _contexto(client, seed_ids, session_factory)
    await iniciar(client, reserva, "mercadopago")
    await configurar(session_factory, sena_porcentaje=Decimal("40.00"))
    g = await client.get(f"/api/public/turnos/{reserva['turno_id']}/sena", headers=cabecera(reserva))
    assert g.status_code == 200 and g.json()["monto"] == "3000.00"
    (pago,) = await pagos_de(session_factory, reserva["turno_id"])
    assert pago.porcentaje_aplicado == Decimal("30.00")
    otra = await reservar(client, seed_ids, local(f, "11:00"))
    r = await iniciar(client, otra, "mercadopago")  # una seña nueva sí usa el 40%
    assert r.json()["monto"] == "4000.00"


async def test_get_sin_pago_iniciado_devuelve_estado_pago_null_con_el_monto_a_pagar(
        client, seed_ids, session_factory, pasarela) -> None:
    _, reserva = await _contexto(client, seed_ids, session_factory)
    g = await client.get(f"/api/public/turnos/{reserva['turno_id']}/sena", headers=cabecera(reserva))
    body = g.json()
    assert g.status_code == 200
    assert (body["estado_turno"], body["estado_pago"], body["monto"]) == ("en_espera", None, "3000.00")
    assert body["vence_en"] and body["vencida"] is False
    assert set(body["medios_habilitados"]) == {"mercadopago", "transferencia"}


async def test_get_con_pago_acreditado_devuelve_reservado_y_acreditado(
        client, seed_ids, session_factory, pasarela) -> None:
    _, reserva = await _contexto(client, seed_ids, session_factory)
    await iniciar(client, reserva, "mercadopago")
    async with session_factory() as s:  # estado de datos equivalente a una acreditación ya hecha
        await s.execute(update(PagoSena).values(estado="acreditado", acreditado_en=datetime.now(timezone.utc)))
        await s.execute(update(Turno).where(Turno.id == reserva["turno_id"])
                        .values(estado="reservado", en_espera_vence_en=None))
        await s.commit()
    g = await client.get(f"/api/public/turnos/{reserva['turno_id']}/sena", headers=cabecera(reserva))
    assert (g.json()["estado_turno"], g.json()["estado_pago"]) == ("reservado", "acreditado")
    assert g.json()["vencida"] is False


async def test_get_de_una_pre_reserva_vencida_por_reloj_la_marca_vencida(
        client, seed_ids, session_factory, pasarela) -> None:
    _, reserva = await _contexto(client, seed_ids, session_factory)
    await forzar_vencimiento(session_factory, reserva["turno_id"], datetime.now(timezone.utc) - timedelta(minutes=1))
    g = await client.get(f"/api/public/turnos/{reserva['turno_id']}/sena", headers=cabecera(reserva))
    assert g.status_code == 200 and g.json()["vencida"] is True


async def test_get_incluye_los_datos_del_turno_para_mostrar_la_confirmacion_y_ningun_dato_de_contacto(
        client, seed_ids, session_factory, pasarela) -> None:
    f, reserva = await _contexto(client, seed_ids, session_factory)
    g = await client.get(f"/api/public/turnos/{reserva['turno_id']}/sena", headers=cabecera(reserva))
    body = g.json()
    assert datetime.fromisoformat(body["inicio"]) == local(f, "10:00")
    assert datetime.fromisoformat(body["fin"]) == local(f, "10:30")
    assert (body["tratamiento_nombre"], body["profesional_nombre"]) == ("Limpieza", "Dra. Test")
    assert "Carlos" not in g.text and "+549" not in g.text and "contacto" not in g.text
