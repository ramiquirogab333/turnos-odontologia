"""C-08 (5.1, 5.3): POST /api/panel/turnos (alta manual). PostgreSQL real. Datos 100 % sintéticos (R19)."""

import asyncio
import json
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models.core import RegistroAuditoria
from app.pagos.models import PagoSena
from app.pagos.service import acreditar_pago
from app.turnos.models import Sillon, Turno
from tests.conftest import bearer, crear_sesion_sintetica, crear_usuario_panel
from tests.panel_helpers import (
    LUNES, TELEFONO, cuerpo_alta, insertar_pago, insertar_turno, local, pagos, sembrar_mundo, turno,
)

URL = "/api/panel/turnos"
MARTES = LUNES + timedelta(days=1)
AHORA = local(LUNES, "07:00")


@pytest.fixture
async def mundo(session_factory, clean_db):
    return await sembrar_mundo(session_factory, duracion=45)


@pytest.fixture
async def rec(session_factory, mundo, reloj):
    reloj(AHORA)
    usuario_id, token = await crear_usuario_panel(session_factory, "recepcion@turnos.test", ["recepcion"])
    return {"id": usuario_id, "cab": bearer(token)}


async def _cantidad(session_factory, modelo=Turno) -> int:
    async with session_factory() as s:
        return (await s.execute(select(func.count()).select_from(modelo))).scalar_one()


async def _auditorias(session_factory, origen: str) -> list[RegistroAuditoria]:
    async with session_factory() as s:
        filas = (await s.execute(select(RegistroAuditoria))).scalars().all()
    return [f for f in filas if (f.datos_despues or {}).get("origen") == origen]


# --- happy path --------------------------------------------------------------------------------------------

async def test_alta_en_un_horario_libre_deriva_el_fin_asigna_sillon_y_no_crea_pago(
        client, rec, mundo, session_factory) -> None:
    r = await client.post(URL, json=cuerpo_alta(mundo, local(MARTES, "11:00")), headers=rec["cab"])
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["inicio"] == "2031-11-18T11:00:00-03:00" and j["fin"] == "2031-11-18T11:45:00-03:00"
    assert (j["estado"], j["origen"]) == ("reservado", "manual")
    assert j["sillon_id"] in (mundo["s1"], mundo["s2"]) and len(j["codigo_gestion"]) >= 8
    t = await turno(session_factory, j["id"])
    assert (t.origen, t.estado, t.paciente_id) == ("manual", "reservado", None)
    assert (t.contacto_nombre, t.contacto_telefono) == ("Carlos Sintético", TELEFONO)
    assert t.codigo_gestion == j["codigo_gestion"] and t.en_espera_vence_en is None
    assert await pagos(session_factory, j["id"]) == []  # O7: sin seña
    agenda = await client.get("/api/panel/agenda", params={"vista": "dia", "fecha": MARTES.isoformat()},
                              headers=rec["cab"])
    (en_agenda,) = agenda.json()["turnos"]
    assert (en_agenda["id"], en_agenda["origen"], en_agenda["sena"], en_agenda["bloquea_agenda"]) == (
        j["id"], "manual", None, True)
    assert "codigo_gestion" not in agenda.text  # el código se devuelve una sola vez


async def test_el_alta_usa_la_duracion_vigente_del_tratamiento(client, rec, mundo, session_factory) -> None:
    from sqlalchemy import update

    from app.turnos.models import Tratamiento

    async with session_factory() as s:
        await s.execute(update(Tratamiento).where(Tratamiento.id == mundo["trat"]).values(duracion_minutos=60))
        await s.commit()
    r = await client.post(URL, json=cuerpo_alta(mundo, local(MARTES, "10:00")), headers=rec["cab"])
    assert r.json()["fin"] == "2031-11-18T11:00:00-03:00"


async def test_con_sillon_indicado_y_libre_se_usa_ese(client, rec, mundo) -> None:
    r = await client.post(URL, json=cuerpo_alta(mundo, local(MARTES, "11:00"), sillon_id=mundo["s2"]),
                          headers=rec["cab"])
    assert r.status_code == 201 and r.json()["sillon_id"] == mundo["s2"]


async def test_sin_sillon_asigna_uno_libre_cuando_el_primero_esta_ocupado(client, rec, mundo, session_factory) -> None:
    await insertar_turno(session_factory, mundo, local(MARTES, "11:00"), prof="bruno", sillon="s1")
    r = await client.post(URL, json=cuerpo_alta(mundo, local(MARTES, "11:00")), headers=rec["cab"])
    assert r.status_code == 201 and r.json()["sillon_id"] == mundo["s2"]


# --- conflictos --------------------------------------------------------------------------------------------

async def test_profesional_ocupada_es_409_con_alternativas_y_no_crea_nada(client, rec, mundo, session_factory) -> None:
    await insertar_turno(session_factory, mundo, local(MARTES, "11:00"), minutos=45)
    antes = await _cantidad(session_factory)
    r = await client.post(URL, json=cuerpo_alta(mundo, local(MARTES, "11:15")), headers=rec["cab"])
    assert r.status_code == 409, r.text
    assert r.json()["motivo"] == "profesional" and r.json()["alternativas"]
    assert await _cantidad(session_factory) == antes
    assert await _auditorias(session_factory, "alta_manual_panel") == []


async def test_sillon_indicado_ocupado_es_409_sillon(client, rec, mundo, session_factory) -> None:
    await insertar_turno(session_factory, mundo, local(MARTES, "11:00"), prof="bruno", sillon="s2")
    r = await client.post(URL, json=cuerpo_alta(mundo, local(MARTES, "11:00"), sillon_id=mundo["s2"]),
                          headers=rec["cab"])
    assert r.status_code == 409 and r.json()["motivo"] == "sillon" and r.json()["alternativas"] is not None


async def test_sillon_indicado_inactivo_es_409_sillon(client, rec, mundo, session_factory) -> None:
    async with session_factory() as s:
        sillon = Sillon(nombre="Sillón 9", estado="inactivo")
        s.add(sillon)
        await s.commit()
        inactivo = int(sillon.id)
    r = await client.post(URL, json=cuerpo_alta(mundo, local(MARTES, "11:00"), sillon_id=inactivo), headers=rec["cab"])
    assert r.status_code == 409 and r.json()["motivo"] == "sillon"


async def test_sillon_o_profesional_o_tratamiento_inexistente_es_422(client, rec, mundo) -> None:
    for campo in ("sillon_id", "profesional_id", "tratamiento_id"):
        r = await client.post(URL, json=cuerpo_alta(mundo, local(MARTES, "11:00"), **{campo: 999999}),
                              headers=rec["cab"])
        assert r.status_code == 422, (campo, r.text)


async def test_dos_altas_simultaneas_son_un_201_y_un_409_nunca_500(client, rec, mundo, session_factory) -> None:
    cuerpo = cuerpo_alta(mundo, local(MARTES, "11:00"))
    a, b = await asyncio.gather(client.post(URL, json=cuerpo, headers=rec["cab"]),
                                client.post(URL, json=cuerpo, headers=rec["cab"]))
    assert sorted([a.status_code, b.status_code]) == [201, 409]
    assert await _cantidad(session_factory) == 1


async def test_si_el_exclude_dispara_a_pesar_del_prechequeo_la_respuesta_es_409(
        client, rec, mundo, session_factory, monkeypatch) -> None:
    await insertar_turno(session_factory, mundo, local(MARTES, "11:00"), minutos=45)

    async def sin_bloqueos(*_a, **_k):  # el pre-chequeo "no ve" el turno: queda solo la garantía de la base (R5)
        return []

    monkeypatch.setattr("app.panel.service._cargar_bloqueos", sin_bloqueos)
    r = await client.post(URL, json=cuerpo_alta(mundo, local(MARTES, "11:15")), headers=rec["cab"])
    assert r.status_code == 409, r.text
    assert r.json()["motivo"] in ("profesional", "sillon") and "alternativas" in r.json()
    assert await _cantidad(session_factory) == 1


# --- disponibilidad, pasado y validación ------------------------------------------------------------------

async def test_fuera_de_la_franja_es_422_fuera_de_disponibilidad(client, rec, mundo, session_factory) -> None:
    r = await client.post(URL, json=cuerpo_alta(mundo, local(MARTES, "20:00")), headers=rec["cab"])
    assert r.status_code == 422 and r.json()["motivo"] == "fuera_de_disponibilidad"
    assert await _cantidad(session_factory) == 0


async def test_dia_sin_franja_o_franja_inactiva_es_422(client, rec, mundo, session_factory) -> None:
    from sqlalchemy import update

    from app.models.core import Disponibilidad

    async with session_factory() as s:
        await s.execute(update(Disponibilidad).where(Disponibilidad.profesional_id == mundo["ana"])
                        .values(is_active=False))
        await s.commit()
    r = await client.post(URL, json=cuerpo_alta(mundo, local(MARTES, "11:00")), headers=rec["cab"])
    assert r.status_code == 422 and r.json()["motivo"] == "fuera_de_disponibilidad"


async def test_el_inicio_pasado_es_422_y_el_inicio_exactamente_ahora_tambien(client, rec, mundo, session_factory) -> None:
    for inicio in (AHORA - timedelta(hours=1), AHORA):
        r = await client.post(URL, json=cuerpo_alta(mundo, inicio), headers=rec["cab"])
        assert r.status_code == 422, (inicio, r.text)
    assert await _cantidad(session_factory) == 0


@pytest.mark.parametrize("extra", [
    {"telefono": "11 5555 6666"}, {"telefono": "+0123"}, {"nombre": "  "}, {"nombre": "x" * 201},
    {"fin": "2031-11-18T12:00:00-03:00"}, {"estado": "en_espera"}, {"origen": "web"}, {"codigo_gestion": "abcdefgh"},
])
async def test_cuerpos_invalidos_son_422_y_no_crean_nada(client, rec, mundo, session_factory, extra) -> None:
    r = await client.post(URL, json=cuerpo_alta(mundo, local(MARTES, "11:00"), **extra), headers=rec["cab"])
    assert r.status_code == 422, r.text
    assert await _cantidad(session_factory) == 0


async def test_inicio_sin_zona_horaria_es_422(client, rec, mundo) -> None:
    r = await client.post(URL, json={**cuerpo_alta(mundo, local(MARTES, "11:00")), "inicio": "2031-11-18T11:00:00"},
                          headers=rec["cab"])
    assert r.status_code == 422


async def test_franja_justa_12_30_entra_y_12_45_no(client, session_factory, clean_db, reloj) -> None:
    reloj(AHORA)
    mundo = await sembrar_mundo(session_factory, franja=("09:00", "13:00"), duracion=30)
    _, token = await crear_usuario_panel(session_factory, "recepcion@turnos.test", ["recepcion"])
    cab = bearer(token)
    assert (await client.post(URL, json=cuerpo_alta(mundo, local(MARTES, "12:30")), headers=cab)).status_code == 201
    assert (await client.post(URL, json=cuerpo_alta(mundo, local(MARTES, "12:45")), headers=cab)).status_code == 422


# --- pre-reserva ---------------------------------------------------------------------------------------------

async def test_alta_sobre_una_en_espera_es_201_y_el_pago_posterior_queda_a_reembolsar(
        client, rec, mundo, session_factory) -> None:
    en_espera = await insertar_turno(session_factory, mundo, local(MARTES, "10:00"), estado="en_espera",
                                     vence=local(MARTES, "10:00"), nombre="Sofía Muestra")
    pago_id = await insertar_pago(session_factory, en_espera, "pendiente", medio="mercadopago",
                                  vence=local(MARTES, "10:00"))
    r = await client.post(URL, json=cuerpo_alta(mundo, local(MARTES, "10:00")), headers=rec["cab"])
    assert r.status_code == 201, r.text
    manual_id = r.json()["id"]
    async with session_factory() as s:
        resultado = await acreditar_pago(s, pago_id, mp_payment_id="PAY-MANUAL", monto_reportado=Decimal("3000.00"),
                                         moneda_reportada="ARS")
    assert resultado.efecto == "a_reembolsar"
    (pago,) = await pagos(session_factory, en_espera)
    assert pago.estado == "a_reembolsar"
    assert (await turno(session_factory, en_espera)).estado == "cancelado"  # no pasa a reservado (RN-SN-05)
    assert (await turno(session_factory, manual_id)).estado == "reservado"


# --- RBAC ---------------------------------------------------------------------------------------------------

async def test_odontologo_es_403_sin_token_es_401_y_refresh_como_bearer_es_401(
        client, mundo, session_factory, reloj) -> None:
    reloj(AHORA)
    uid, token = await crear_usuario_panel(session_factory, "dra@turnos.test", ["odontologo"],
                                           profesional_id=mundo["ana"])
    cuerpo = cuerpo_alta(mundo, local(MARTES, "11:00"))
    assert (await client.post(URL, json=cuerpo, headers=bearer(token))).status_code == 403
    assert (await client.post(URL, json=cuerpo)).status_code == 401
    _, _, refresh = await crear_sesion_sintetica(session_factory, uid, "dra@turnos.test", ["recepcion"])
    assert (await client.post(URL, json=cuerpo, headers=bearer(refresh))).status_code == 401
    assert await _cantidad(session_factory) == 0


async def test_admin_tambien_puede_dar_de_alta(client, mundo, session_factory, reloj) -> None:
    reloj(AHORA)
    _, token = await crear_usuario_panel(session_factory, "admin@turnos.test", ["admin"])
    r = await client.post(URL, json=cuerpo_alta(mundo, local(MARTES, "11:00")), headers=bearer(token))
    assert r.status_code == 201


# --- auditoría ----------------------------------------------------------------------------------------------

async def test_el_alta_deja_auditoria_con_usuario_y_sin_datos_personales(client, rec, mundo, session_factory) -> None:
    r = await client.post(URL, json=cuerpo_alta(mundo, local(MARTES, "11:00")), headers=rec["cab"])
    assert r.status_code == 201
    (registro,) = await _auditorias(session_factory, "alta_manual_panel")
    assert registro.usuario_id == rec["id"] and registro.entidad == "turno"
    assert registro.entidad_id == str(r.json()["id"])
    texto = json.dumps([registro.datos_antes, registro.datos_despues], ensure_ascii=False)
    for dato in ("Carlos", "Sintético", TELEFONO, r.json()["codigo_gestion"]):
        assert dato not in texto


# --- gestión por el paciente de un turno manual -------------------------------------------------------------

async def test_el_paciente_cancela_un_turno_manual_con_su_codigo_y_no_hay_pagos(
        client, rec, mundo, session_factory, reloj, notificador) -> None:
    creado = (await client.post(URL, json=cuerpo_alta(mundo, local(MARTES, "11:00")), headers=rec["cab"])).json()
    reloj(local(MARTES, "11:00") - timedelta(hours=48))
    r = await client.post("/api/public/gestion/cancelar", headers={"X-Codigo-Gestion": creado["codigo_gestion"]})
    assert r.status_code == 200, r.text
    assert (await turno(session_factory, creado["id"])).estado == "cancelado"
    assert await pagos(session_factory, creado["id"]) == []


# --- 5.3 delta pagos/sena-turno ------------------------------------------------------------------------------

async def test_el_alta_manual_deja_un_unico_registro_de_alta_y_ninguna_acreditacion(
        client, rec, mundo, session_factory) -> None:
    r = await client.post(URL, json=cuerpo_alta(mundo, local(MARTES, "11:00")), headers=rec["cab"])
    assert r.status_code == 201
    assert len(await _auditorias(session_factory, "alta_manual_panel")) == 1
    assert await _auditorias(session_factory, "acreditacion_sena") == []
    assert (await turno(session_factory, r.json()["id"])).estado == "reservado"
    assert await _cantidad(session_factory, PagoSena) == 0
