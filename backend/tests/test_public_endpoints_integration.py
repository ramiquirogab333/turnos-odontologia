"""Integración C-05: endpoints públicos de disponibilidad y reserva (PostgreSQL real).

Strict TDD. Cubre las tareas 1.2 / 1.3 y la terna de escenarios 3.1 / 3.2 / 3.3
a nivel API. Zona horaria de la clínica: America/Argentina/Buenos_Aires (-03:00);
`Disponibilidad.hora_*` son horas locales. Datos 100% sintéticos (R19).
"""

import asyncio
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.core import Disponibilidad, Paciente
from app.turnos.models import Sillon, Turno

TZ = ZoneInfo("America/Argentina/Buenos_Aires")
TELEFONO = "+5491144445555"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fecha_laboral(offset_min: int = 3) -> date:
    """Primer día lunes-viernes (hora local) con al menos `offset_min` días de margen."""
    d = datetime.now(TZ).date() + timedelta(days=offset_min)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _local(fecha: date, hhmm: str) -> datetime:
    return datetime.combine(fecha, time.fromisoformat(hhmm), tzinfo=TZ)


async def _seed_disp(factory: async_sessionmaker[AsyncSession], profesional_id: int, fecha: date,
                     hora_inicio: str = "09:00", hora_fin: str = "17:00", *, is_active: bool = True) -> None:
    async with factory() as s:
        s.add(Disponibilidad(
            profesional_id=profesional_id, dia_semana=fecha.weekday(),
            hora_inicio=time.fromisoformat(hora_inicio), hora_fin=time.fromisoformat(hora_fin),
            is_active=is_active,
        ))
        await s.commit()


async def _seed_turno(factory: async_sessionmaker[AsyncSession], ids: dict[str, int], inicio: datetime,
                      minutos: int = 30, estado: str = "reservado", *, profesional_id: int | None = None,
                      sillon_id: int | None = None) -> None:
    async with factory() as s:
        s.add(Turno(
            profesional_id=profesional_id or ids["profesional_id"], sillon_id=sillon_id or ids["sillon_id"],
            tratamiento_id=ids["tratamiento_id"], inicio=inicio, fin=inicio + timedelta(minutes=minutos),
            estado=estado, en_espera_vence_en=inicio if estado == "en_espera" else None,
        ))
        await s.commit()


def _payload(ids: dict[str, int], inicio: datetime, **over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "nombre": "Carlos Sintético", "telefono": TELEFONO,
        "tratamiento_id": ids["tratamiento_id"], "profesional_id": ids["profesional_id"],
        "inicio": inicio.isoformat(),
    }
    base.update(over)
    return base


async def _slots(client: httpx.AsyncClient, ids: dict[str, int], desde: date, hasta: date | None = None,
                 profesional_id: int | None = None) -> list[dict]:
    r = await client.get("/api/public/disponibilidad", params={
        "profesional_id": profesional_id or ids["profesional_id"], "tratamiento_id": ids["tratamiento_id"],
        "desde": desde.isoformat(), "hasta": (hasta or desde).isoformat(),
    })
    assert r.status_code == 200, r.text
    return r.json()["slots"]


def _inicios(slots: list[dict]) -> list[datetime]:
    return [datetime.fromisoformat(s["inicio"]) for s in slots]


# ---------------------------------------------------------------------------
# 1.2  GET /api/public/disponibilidad
# ---------------------------------------------------------------------------

async def test_disponibilidad_devuelve_slots_de_la_duracion_en_hora_local(client, seed_ids, session_factory) -> None:
    f = _fecha_laboral()
    await _seed_disp(session_factory, seed_ids["profesional_id"], f, "09:00", "17:00")
    slots = await _slots(client, seed_ids, f)
    assert len(slots) == 16  # 8 h / 30 min
    assert datetime.fromisoformat(slots[0]["inicio"]) == _local(f, "09:00")  # 12:00Z, no 09:00Z
    assert datetime.fromisoformat(slots[-1]["fin"]) == _local(f, "17:00")
    for s in slots:
        assert datetime.fromisoformat(s["fin"]) - datetime.fromisoformat(s["inicio"]) == timedelta(minutes=30)
        assert s["profesional_id"] == seed_ids["profesional_id"]
        assert s["sillon_id"] == seed_ids["sillon_id"]


async def test_disponibilidad_la_duracion_del_tratamiento_define_el_tamano_del_slot(
    client, seed_ids, session_factory
) -> None:
    f = _fecha_laboral()
    await _seed_disp(session_factory, seed_ids["profesional_id"], f, "09:00", "17:00")
    async with session_factory() as s:
        from app.turnos.models import Tratamiento
        await s.execute(update(Tratamiento).where(Tratamiento.id == seed_ids["tratamiento_id"])
                        .values(duracion_minutos=60))
        await s.commit()
    slots = await _slots(client, seed_ids, f)
    assert len(slots) == 8
    assert datetime.fromisoformat(slots[1]["inicio"]) == _local(f, "10:00")


async def test_disponibilidad_sin_franja_vigente_devuelve_vacio(client, seed_ids, session_factory) -> None:
    f = _fecha_laboral()
    assert await _slots(client, seed_ids, f) == []  # sin Disponibilidad
    await _seed_disp(session_factory, seed_ids["profesional_id"], f, is_active=False)
    assert await _slots(client, seed_ids, f) == []  # franja inactiva no es vigente (RN-TU-07)


async def test_disponibilidad_respeta_el_dia_de_la_semana(client, seed_ids, session_factory) -> None:
    f = _fecha_laboral()
    await _seed_disp(session_factory, seed_ids["profesional_id"], f)
    assert await _slots(client, seed_ids, f + timedelta(days=1)) == []  # otro día sin franja
    assert len(await _slots(client, seed_ids, f, f + timedelta(days=7))) == 32  # f y f+7 (mismo weekday)


async def test_disponibilidad_excluye_slot_ocupado_por_el_profesional(client, seed_ids, session_factory) -> None:
    f = _fecha_laboral()
    await _seed_disp(session_factory, seed_ids["profesional_id"], f)
    await _seed_turno(session_factory, seed_ids, _local(f, "10:00"))
    inicios = _inicios(await _slots(client, seed_ids, f))
    assert len(inicios) == 15
    assert _local(f, "10:00") not in inicios
    assert _local(f, "09:30") in inicios and _local(f, "10:30") in inicios


async def test_disponibilidad_un_turno_cancelado_no_bloquea_el_slot(client, seed_ids, session_factory) -> None:
    f = _fecha_laboral()
    await _seed_disp(session_factory, seed_ids["profesional_id"], f)
    await _seed_turno(session_factory, seed_ids, _local(f, "10:00"), estado="cancelado")
    assert _local(f, "10:00") in _inicios(await _slots(client, seed_ids, f))


async def test_disponibilidad_considera_el_sillon_ademas_del_profesional(client, seed_pair, session_factory) -> None:
    """P2 ocupa el único sillón activo a las 10:00: P1 (libre) tampoco tiene ese slot."""
    f = _fecha_laboral()
    ids = {"profesional_id": seed_pair["p1"], "sillon_id": seed_pair["s1"], "tratamiento_id": seed_pair["t"]}
    await _seed_disp(session_factory, seed_pair["p1"], f)
    async with session_factory() as s:
        await s.execute(update(Sillon).where(Sillon.id == seed_pair["s2"]).values(estado="inactivo"))
        await s.commit()
    await _seed_turno(session_factory, ids, _local(f, "10:00"), profesional_id=seed_pair["p2"])
    inicios = _inicios(await _slots(client, ids, f))
    assert _local(f, "10:00") not in inicios
    assert _local(f, "09:30") in inicios


async def test_disponibilidad_con_sillon_alternativo_el_slot_sigue_libre(client, seed_pair, session_factory) -> None:
    """Triangulación: con un 2º sillón activo libre, el slot ocupado por P2 sigue disponible para P1."""
    f = _fecha_laboral()
    ids = {"profesional_id": seed_pair["p1"], "sillon_id": seed_pair["s1"], "tratamiento_id": seed_pair["t"]}
    await _seed_disp(session_factory, seed_pair["p1"], f)
    await _seed_turno(session_factory, ids, _local(f, "10:00"), profesional_id=seed_pair["p2"])
    slot = next(s for s in await _slots(client, ids, f) if datetime.fromisoformat(s["inicio"]) == _local(f, "10:00"))
    assert slot["sillon_id"] == seed_pair["s2"]


async def test_disponibilidad_no_ofrece_slots_pasados(client, seed_ids, session_factory) -> None:
    hoy = datetime.now(TZ).date()
    async with session_factory() as s:
        s.add(Disponibilidad(profesional_id=seed_ids["profesional_id"], dia_semana=hoy.weekday(),
                             hora_inicio=time(0, 0), hora_fin=time(23, 59)))
        await s.commit()
    ahora = datetime.now(timezone.utc)
    inicios = _inicios(await _slots(client, seed_ids, hoy))
    assert all(i > ahora for i in inicios)


async def test_disponibilidad_rango_invalido_devuelve_422(client, seed_ids) -> None:
    f = _fecha_laboral()
    p = {"profesional_id": seed_ids["profesional_id"], "tratamiento_id": seed_ids["tratamiento_id"]}
    r = await client.get("/api/public/disponibilidad",
                         params={**p, "desde": f.isoformat(), "hasta": (f - timedelta(days=1)).isoformat()})
    assert r.status_code == 422, r.text
    r = await client.get("/api/public/disponibilidad",
                         params={**p, "desde": f.isoformat(), "hasta": (f + timedelta(days=90)).isoformat()})
    assert r.status_code == 422, r.text


async def test_disponibilidad_referencia_inexistente_devuelve_422(client, seed_ids) -> None:
    f = _fecha_laboral()
    r = await client.get("/api/public/disponibilidad", params={
        "profesional_id": 999999, "tratamiento_id": seed_ids["tratamiento_id"],
        "desde": f.isoformat(), "hasta": f.isoformat()})
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# 1.3 / 3.1  POST /api/public/turnos — Happy Path
# ---------------------------------------------------------------------------

async def test_reserva_happy_path_201_en_espera_con_sena_y_sin_paciente(
    client, seed_ids, session_factory
) -> None:
    """Escenario 3.1 (C-06): Carlos Sintético, 30 min, precio 10000.00 -> 201 `en_espera` con seña de 3000.00."""
    from app.turnos.models import Tratamiento
    from tests.sena_helpers import configurar_transferencia
    f = _fecha_laboral()
    await _seed_disp(session_factory, seed_ids["profesional_id"], f)
    await configurar_transferencia(session_factory)  # la transferencia solo se ofrece con alias y CBU cargados
    async with session_factory() as s:
        await s.execute(update(Tratamiento).where(Tratamiento.id == seed_ids["tratamiento_id"])
                        .values(precio_base=Decimal("10000.00")))
        pacientes_antes = (await s.execute(select(func.count()).select_from(Paciente))).scalar_one()
        await s.commit()
    inicio = _local(f, "10:00")
    r = await client.post("/api/public/turnos", json=_payload(seed_ids, inicio))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["estado"] == "en_espera"
    assert datetime.fromisoformat(body["inicio"]) == inicio
    assert datetime.fromisoformat(body["fin"]) == inicio + timedelta(minutes=30)  # RN-TU-04
    assert len(body["codigo_gestion"]) >= 8
    sena = body["sena"]
    assert sena["monto"] == "3000.00"
    assert datetime.fromisoformat(sena["vence_en"]) <= inicio
    assert datetime.fromisoformat(sena["vence_en"]) > datetime.now(timezone.utc)
    assert sorted(sena["medios_habilitados"]) == ["mercadopago", "transferencia"]
    assert "te devolvemos la seña" in sena["texto_politica_reembolso"]

    async with session_factory() as s:
        turno = (await s.execute(select(Turno).where(Turno.id == body["turno_id"]))).scalar_one()
        assert turno.estado == "en_espera" and turno.en_espera_vence_en == datetime.fromisoformat(sena["vence_en"])
        assert turno.fin - turno.inicio == timedelta(minutes=30)
        assert turno.sillon_id == seed_ids["sillon_id"] and turno.profesional_id == seed_ids["profesional_id"]
        assert turno.codigo_gestion == body["codigo_gestion"]  # el código sirve: está persistido
        assert turno.contacto_nombre == "Carlos Sintético"
        assert turno.contacto_telefono == TELEFONO
        assert (await s.execute(select(func.count()).select_from(Paciente))).scalar_one() == pacientes_antes


async def test_reserva_en_espera_vence_a_los_30_minutos_configurados(client, seed_ids, session_factory) -> None:
    """RN-SN-07: el vencimiento inicial usa expiracion_mp_minutos (30), acotado al inicio del turno."""
    f = _fecha_laboral()
    await _seed_disp(session_factory, seed_ids["profesional_id"], f)
    antes = datetime.now(timezone.utc)
    r = await client.post("/api/public/turnos", json=_payload(seed_ids, _local(f, "10:00")))
    vence = datetime.fromisoformat(r.json()["sena"]["vence_en"])
    assert antes + timedelta(minutes=29) < vence < datetime.now(timezone.utc) + timedelta(minutes=31)


async def test_reserva_con_precio_cero_nace_reservado_sin_sena(client, seed_ids, session_factory) -> None:
    """P4 / RN-SN-06: tratamiento exento de seña -> `reservado` directo, bloquea agenda y no lleva bloque `sena`."""
    from app.turnos.models import Tratamiento
    f = _fecha_laboral()
    await _seed_disp(session_factory, seed_ids["profesional_id"], f)
    async with session_factory() as s:
        await s.execute(update(Tratamiento).where(Tratamiento.id == seed_ids["tratamiento_id"])
                        .values(precio_base=Decimal("0.00")))
        await s.commit()
    r = await client.post("/api/public/turnos", json=_payload(seed_ids, _local(f, "10:00")))
    assert r.status_code == 201, r.text
    assert r.json()["estado"] == "reservado" and r.json()["sena"] is None
    assert _local(f, "10:00") not in _inicios(await _slots(client, seed_ids, f))
    async with session_factory() as s:
        turno = (await s.execute(select(Turno))).scalar_one()
        assert turno.estado == "reservado" and turno.en_espera_vence_en is None


async def test_la_auditoria_de_la_reserva_no_guarda_pii(client, seed_ids, session_factory) -> None:
    from app.models.core import RegistroAuditoria
    f = _fecha_laboral()
    await _seed_disp(session_factory, seed_ids["profesional_id"], f)
    assert (await client.post("/api/public/turnos", json=_payload(seed_ids, _local(f, "10:00")))).status_code == 201
    async with session_factory() as s:
        aud = (await s.execute(select(RegistroAuditoria).where(RegistroAuditoria.entidad == "turno"))).scalar_one()
    assert aud.datos_despues["origen"] == "reserva_publica" and aud.datos_despues["estado"] == "en_espera"
    assert "Carlos" not in str(aud.datos_despues) and TELEFONO not in str(aud.datos_despues)


async def test_reserva_fin_se_deriva_de_la_duracion_ignorando_cualquier_fin_del_cliente(
    client, seed_ids, session_factory
) -> None:
    """Triangulación RN-TU-04: tratamiento de 60 min -> fin = inicio + 60; el cliente no puede fijar `fin`."""
    from app.turnos.models import Tratamiento
    f = _fecha_laboral()
    await _seed_disp(session_factory, seed_ids["profesional_id"], f)
    async with session_factory() as s:
        await s.execute(update(Tratamiento).where(Tratamiento.id == seed_ids["tratamiento_id"])
                        .values(duracion_minutos=60))
        await s.commit()
    inicio = _local(f, "11:00")
    r = await client.post("/api/public/turnos", json=_payload(seed_ids, inicio))
    assert r.status_code == 201, r.text
    assert datetime.fromisoformat(r.json()["fin"]) == inicio + timedelta(minutes=60)
    r2 = await client.post("/api/public/turnos", json={**_payload(seed_ids, _local(f, "14:00")),
                                                       "fin": _local(f, "14:05").isoformat()})
    assert r2.status_code == 422  # extra=forbid


async def test_reserva_codigos_de_gestion_son_unicos(client, seed_ids, session_factory) -> None:
    f = _fecha_laboral()
    await _seed_disp(session_factory, seed_ids["profesional_id"], f)
    r1 = await client.post("/api/public/turnos", json=_payload(seed_ids, _local(f, "10:00")))
    r2 = await client.post("/api/public/turnos", json=_payload(seed_ids, _local(f, "10:30")))
    assert r1.status_code == r2.status_code == 201
    assert r1.json()["codigo_gestion"] != r2.json()["codigo_gestion"]


async def test_reserva_en_espera_no_ocupa_el_slot_en_la_disponibilidad(client, seed_ids, session_factory) -> None:
    """R8: un `en_espera` no bloquea agenda; el horario se sigue ofreciendo hasta acreditar la seña."""
    f = _fecha_laboral()
    await _seed_disp(session_factory, seed_ids["profesional_id"], f)
    r = await client.post("/api/public/turnos", json=_payload(seed_ids, _local(f, "10:00")))
    assert r.status_code == 201 and r.json()["estado"] == "en_espera"
    assert _local(f, "10:00") in _inicios(await _slots(client, seed_ids, f))


async def test_disponibilidad_ofrece_un_horario_ocupado_solo_por_un_en_espera(client, seed_ids, session_factory) -> None:
    f = _fecha_laboral()
    await _seed_disp(session_factory, seed_ids["profesional_id"], f)
    await _seed_turno(session_factory, seed_ids, _local(f, "10:00"), estado="en_espera")
    inicios = _inicios(await _slots(client, seed_ids, f))
    assert len(inicios) == 16 and _local(f, "10:00") in inicios


# ---------------------------------------------------------------------------
# RN-TU-07: solo dentro de la disponibilidad vigente
# ---------------------------------------------------------------------------

async def test_reserva_fuera_de_la_franja_de_atencion_devuelve_422_y_no_persiste(
    client, seed_ids, session_factory
) -> None:
    f = _fecha_laboral()
    await _seed_disp(session_factory, seed_ids["profesional_id"], f, "09:00", "17:00")
    for hhmm in ("08:30", "16:45", "17:00", "22:00"):  # antes, termina fuera, justo al cierre, de noche
        r = await client.post("/api/public/turnos", json=_payload(seed_ids, _local(f, hhmm)))
        assert r.status_code == 422, (hhmm, r.text)
    async with session_factory() as s:
        assert (await s.execute(select(func.count()).select_from(Turno))).scalar_one() == 0


async def test_reserva_en_dia_sin_franja_o_franja_inactiva_devuelve_422(client, seed_ids, session_factory) -> None:
    f = _fecha_laboral()
    assert (await client.post("/api/public/turnos", json=_payload(seed_ids, _local(f, "10:00")))).status_code == 422
    await _seed_disp(session_factory, seed_ids["profesional_id"], f, is_active=False)
    assert (await client.post("/api/public/turnos", json=_payload(seed_ids, _local(f, "10:00")))).status_code == 422


async def test_reserva_en_el_ultimo_slot_valido_del_horario_es_201(client, seed_ids, session_factory) -> None:
    """Borde: 16:30 + 30 min = 17:00 exacto, fin == cierre -> permitido."""
    f = _fecha_laboral()
    await _seed_disp(session_factory, seed_ids["profesional_id"], f, "09:00", "17:00")
    r = await client.post("/api/public/turnos", json=_payload(seed_ids, _local(f, "16:30")))
    assert r.status_code == 201, r.text


# ---------------------------------------------------------------------------
# 3.2  Error de negocio: solape / carrera real
# ---------------------------------------------------------------------------

async def test_reserva_en_slot_ocupado_devuelve_409_con_motivo_y_alternativas_sin_persistir(
    client, seed_ids, session_factory
) -> None:
    f = _fecha_laboral()
    await _seed_disp(session_factory, seed_ids["profesional_id"], f)
    await _seed_turno(session_factory, seed_ids, _local(f, "10:00"))
    r = await client.post("/api/public/turnos", json=_payload(seed_ids, _local(f, "10:00")))
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["motivo"] == "profesional" and "profesional" in body["detail"]
    alts = [datetime.fromisoformat(a["inicio"]) for a in body["alternativas"]]
    assert alts and _local(f, "10:00") not in alts and all(a >= _local(f, "10:00") for a in alts)
    assert alts[0] == _local(f, "10:30")  # la primera libre contigua
    async with session_factory() as s:
        assert (await s.execute(select(func.count()).select_from(Turno))).scalar_one() == 1  # solo el sembrado


async def test_reserva_solapada_parcialmente_tambien_es_409(client, seed_ids, session_factory) -> None:
    """Triangulación: turno de 30' a las 10:00; pedir 10:15 (60') solapa [10:15,11:15) con [10:00,10:30)."""
    from app.turnos.models import Tratamiento
    f = _fecha_laboral()
    await _seed_disp(session_factory, seed_ids["profesional_id"], f)
    await _seed_turno(session_factory, seed_ids, _local(f, "10:00"))
    async with session_factory() as s:
        await s.execute(update(Tratamiento).where(Tratamiento.id == seed_ids["tratamiento_id"])
                        .values(duracion_minutos=60))
        await s.commit()
    r = await client.post("/api/public/turnos", json=_payload(seed_ids, _local(f, "10:15")))
    assert r.status_code == 409, r.text
    # contiguo (10:30) NO solapa: rango semiabierto [)
    assert (await client.post("/api/public/turnos", json=_payload(seed_ids, _local(f, "10:30")))).status_code == 201


async def test_carrera_real_mismo_slot_dos_201_en_espera_y_la_competencia_se_define_al_acreditar(
    client, seed_ids, session_factory
) -> None:
    """P7: dos peticiones simultáneas al mismo slot son 201 `en_espera` (R8); el bloqueo lo decide la acreditación."""
    f = _fecha_laboral()
    await _seed_disp(session_factory, seed_ids["profesional_id"], f)
    inicio = _local(f, "11:00")
    for _ in range(5):  # repetir: una carrera acertada una vez no demuestra nada
        async with session_factory() as s:
            await s.execute(Turno.__table__.delete())
            await s.commit()
        a, b = await asyncio.gather(
            client.post("/api/public/turnos", json=_payload(seed_ids, inicio)),
            client.post("/api/public/turnos", json=_payload(seed_ids, inicio, nombre="María Sintética")),
        )
        assert (a.status_code, b.status_code) == (201, 201), (a.text, b.text)
        assert a.json()["estado"] == b.json()["estado"] == "en_espera"
        assert a.json()["codigo_gestion"] != b.json()["codigo_gestion"]
        async with session_factory() as s:
            estados = (await s.execute(select(Turno.estado))).scalars().all()
            assert sorted(estados) == ["en_espera", "en_espera"]  # ninguno bloquea


async def test_carrera_de_cuatro_peticiones_deja_cuatro_pre_reservas_y_ningun_bloqueo(
    client, seed_ids, session_factory
) -> None:
    f = _fecha_laboral()
    await _seed_disp(session_factory, seed_ids["profesional_id"], f)
    inicio = _local(f, "12:00")
    rs = await asyncio.gather(*[client.post("/api/public/turnos", json=_payload(seed_ids, inicio)) for _ in range(4)])
    assert [r.status_code for r in rs] == [201, 201, 201, 201], [r.text for r in rs]
    async with session_factory() as s:
        assert (await s.execute(select(func.count()).select_from(Turno).where(Turno.estado == "en_espera"))
                ).scalar_one() == 4


async def test_carrera_entre_dos_profesionales_por_el_unico_sillon_son_dos_201_en_espera(
    client, seed_pair, session_factory
) -> None:
    """Profesionales distintos y un único sillón: ambas son pre-reservas (201); el sillón se disputa al acreditar."""
    f = _fecha_laboral()
    async with session_factory() as s:
        await s.execute(update(Sillon).where(Sillon.id == seed_pair["s2"]).values(estado="inactivo"))
        await s.commit()
    for p in (seed_pair["p1"], seed_pair["p2"]):
        await _seed_disp(session_factory, p, f)
    ids1 = {"profesional_id": seed_pair["p1"], "tratamiento_id": seed_pair["t"]}
    ids2 = {"profesional_id": seed_pair["p2"], "tratamiento_id": seed_pair["t"]}
    inicio = _local(f, "10:00")
    a, b = await asyncio.gather(
        client.post("/api/public/turnos", json=_payload(ids1, inicio)),
        client.post("/api/public/turnos", json=_payload(ids2, inicio)),
    )
    assert (a.status_code, b.status_code) == (201, 201), (a.text, b.text)


# ---------------------------------------------------------------------------
# 3.3  Caso de borde: teléfono inválido en el último slot del horario de atención
# ---------------------------------------------------------------------------

async def test_telefono_invalido_en_ultimo_slot_422_sin_bloqueo_ni_registros_huerfanos(
    client, seed_ids, session_factory
) -> None:
    f = _fecha_laboral()
    await _seed_disp(session_factory, seed_ids["profesional_id"], f, "09:00", "17:00")
    ultimo = _local(f, "16:30")
    async with session_factory() as s:
        pacientes_antes = (await s.execute(select(func.count()).select_from(Paciente))).scalar_one()

    r = await client.post("/api/public/turnos", json=_payload(seed_ids, ultimo, telefono="1234"))
    assert r.status_code == 422, r.text
    assert any(e["loc"][-1] == "telefono" for e in r.json()["detail"])

    async with session_factory() as s:
        assert (await s.execute(select(func.count()).select_from(Turno))).scalar_one() == 0
        assert (await s.execute(select(func.count()).select_from(Paciente))).scalar_one() == pacientes_antes
    assert ultimo in _inicios(await _slots(client, seed_ids, f))  # el slot sigue libre
    assert (await client.post("/api/public/turnos", json=_payload(seed_ids, ultimo))).status_code == 201


async def test_telefono_sin_codigo_de_pais_en_ultimo_slot_tambien_es_422(client, seed_ids, session_factory) -> None:
    f = _fecha_laboral()
    await _seed_disp(session_factory, seed_ids["profesional_id"], f, "09:00", "17:00")
    r = await client.post("/api/public/turnos", json=_payload(seed_ids, _local(f, "16:30"), telefono="5491144445555"))
    assert r.status_code == 422
    async with session_factory() as s:
        assert (await s.execute(select(func.count()).select_from(Turno))).scalar_one() == 0


# ---------------------------------------------------------------------------
# Validaciones de borde adicionales
# ---------------------------------------------------------------------------

async def test_reserva_inicio_pasado_422(client, seed_ids) -> None:
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    assert (await client.post("/api/public/turnos", json=_payload(seed_ids, past))).status_code == 422


async def test_reserva_fk_inexistente_422(client, seed_ids, session_factory) -> None:
    f = _fecha_laboral()
    r = await client.post("/api/public/turnos", json=_payload(seed_ids, _local(f, "10:00"), profesional_id=999999))
    assert r.status_code == 422
    r = await client.post("/api/public/turnos", json=_payload(seed_ids, _local(f, "10:00"), tratamiento_id=999999))
    assert r.status_code == 422


async def test_reserva_sin_sillon_activo_devuelve_409_sillon(client, seed_ids, session_factory) -> None:
    f = _fecha_laboral()
    await _seed_disp(session_factory, seed_ids["profesional_id"], f)
    async with session_factory() as s:
        await s.execute(update(Sillon).where(Sillon.id == seed_ids["sillon_id"]).values(estado="mantenimiento"))
        await s.commit()
    r = await client.post("/api/public/turnos", json=_payload(seed_ids, _local(f, "10:00")))
    assert r.status_code == 409 and r.json()["motivo"] == "sillon", r.text


async def test_reserva_no_requiere_autenticacion_ni_crea_pacientes(client, seed_ids, session_factory) -> None:
    """RN-TU-06: sin header Authorization y sin crear `paciente` (el contacto vive en el turno)."""
    f = _fecha_laboral()
    await _seed_disp(session_factory, seed_ids["profesional_id"], f)
    async with session_factory() as s:
        antes = (await s.execute(select(func.count()).select_from(Paciente))).scalar_one()
    r = await client.post("/api/public/turnos", json=_payload(seed_ids, _local(f, "10:00")))
    assert r.status_code == 201 and "authorization" not in r.request.headers
    async with session_factory() as s:
        assert (await s.execute(select(func.count()).select_from(Paciente))).scalar_one() == antes
