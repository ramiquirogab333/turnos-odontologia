"""RED (task 3.1/3.2): HTTP contract for POST /api/turnos + GET /api/health."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import future_iso, past_iso


async def test_health_ok(client) -> None:
    r = await client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


async def test_creacion_valida_devuelve_201_con_fin_derivado(client, seed_ids) -> None:
    inicio = future_iso(120)
    r = await client.post("/api/turnos", json={**seed_ids, "inicio": inicio})
    assert r.status_code == 201, r.text
    body = r.json()
    esperado = datetime.fromisoformat(inicio) + timedelta(minutes=30)
    assert datetime.fromisoformat(body["fin"]) == esperado
    assert body["profesional_id"] == seed_ids["profesional_id"]
    assert body["estado"] == "reservado"


async def test_fin_enviado_por_cliente_devuelve_422(client, seed_ids) -> None:
    payload = {**seed_ids, "inicio": future_iso(120), "fin": future_iso(180)}
    r = await client.post("/api/turnos", json=payload)
    assert r.status_code == 422


async def test_inicio_pasado_devuelve_422(client, seed_ids) -> None:
    r = await client.post("/api/turnos", json={**seed_ids, "inicio": past_iso(30)})
    assert r.status_code == 422


@pytest.mark.parametrize("campo", ["profesional_id", "sillon_id", "tratamiento_id", "inicio"])
async def test_campo_faltante_devuelve_422(client, seed_ids, campo) -> None:
    payload = {**seed_ids, "inicio": future_iso(120)}
    del payload[campo]
    r = await client.post("/api/turnos", json=payload)
    assert r.status_code == 422


async def test_fk_inexistente_devuelve_422(client, seed_ids) -> None:
    payload = {**seed_ids, "inicio": future_iso(120), "profesional_id": 999999}
    r = await client.post("/api/turnos", json=payload)
    assert r.status_code == 422


async def test_solape_profesional_devuelve_409(client, seed_ids) -> None:
    inicio = future_iso(120)
    r1 = await client.post("/api/turnos", json={**seed_ids, "inicio": inicio})
    assert r1.status_code == 201
    solapado = (datetime.fromisoformat(inicio) + timedelta(minutes=15)).isoformat()
    r2 = await client.post("/api/turnos", json={**seed_ids, "inicio": solapado})
    assert r2.status_code == 409
    assert r2.json()["motivo"] == "profesional"


async def test_solape_sillon_devuelve_409(client, seed_pair) -> None:
    inicio = future_iso(120)
    primero = {
        "profesional_id": seed_pair["p1"],
        "sillon_id": seed_pair["s1"],
        "tratamiento_id": seed_pair["t"],
        "inicio": inicio,
    }
    r1 = await client.post("/api/turnos", json=primero)
    assert r1.status_code == 201
    solapado = (datetime.fromisoformat(inicio) + timedelta(minutes=15)).isoformat()
    segundo = {
        "profesional_id": seed_pair["p2"],  # profesional distinto, mismo sillon
        "sillon_id": seed_pair["s1"],
        "tratamiento_id": seed_pair["t"],
        "inicio": solapado,
    }
    r2 = await client.post("/api/turnos", json=segundo)
    assert r2.status_code == 409
    assert r2.json()["motivo"] == "sillon"


async def test_slots_adyacentes_devuelven_201(client, seed_ids) -> None:
    inicio = future_iso(120)
    r1 = await client.post("/api/turnos", json={**seed_ids, "inicio": inicio})
    assert r1.status_code == 201
    siguiente = (datetime.fromisoformat(inicio) + timedelta(minutes=30)).isoformat()
    r2 = await client.post("/api/turnos", json={**seed_ids, "inicio": siguiente})
    assert r2.status_code == 201, r2.text


async def test_mismo_horario_distintos_recursos_devuelve_201(client, seed_pair) -> None:
    inicio = future_iso(120)
    r1 = await client.post(
        "/api/turnos",
        json={
            "profesional_id": seed_pair["p1"],
            "sillon_id": seed_pair["s1"],
            "tratamiento_id": seed_pair["t"],
            "inicio": inicio,
        },
    )
    assert r1.status_code == 201
    r2 = await client.post(
        "/api/turnos",
        json={
            "profesional_id": seed_pair["p2"],
            "sillon_id": seed_pair["s2"],
            "tratamiento_id": seed_pair["t"],
            "inicio": inicio,
        },
    )
    assert r2.status_code == 201, r2.text


async def test_estado_cancelado_no_bloquea(client, seed_ids, session_factory) -> None:
    from sqlalchemy import text

    inicio = future_iso(120)
    r1 = await client.post("/api/turnos", json={**seed_ids, "inicio": inicio})
    assert r1.status_code == 201
    async with session_factory() as s:
        await s.execute(text("UPDATE turno SET estado='cancelado' WHERE id=:i"), {"i": r1.json()["id"]})
        await s.commit()
    r2 = await client.post("/api/turnos", json={**seed_ids, "inicio": inicio})
    assert r2.status_code == 201, r2.text


async def test_carrera_concurrente_un_201_y_un_409(client, seed_ids) -> None:
    payload = {**seed_ids, "inicio": future_iso(180)}
    results = await asyncio.gather(
        client.post("/api/turnos", json=payload),
        client.post("/api/turnos", json=payload),
    )
    assert sorted(r.status_code for r in results) == [201, 409]
    assert results[0].json().get("motivo", None) in (None, "profesional", "sillon")
    assert results[1].json().get("motivo", None) in (None, "profesional", "sillon")


async def test_ningun_solape_llega_como_500(client, seed_ids) -> None:
    inicio = future_iso(120)
    assert (await client.post("/api/turnos", json={**seed_ids, "inicio": inicio})).status_code == 201
    for delta in (0, 10, 29):
        solapado = (datetime.fromisoformat(inicio) + timedelta(minutes=delta)).isoformat()
        r = await client.post("/api/turnos", json={**seed_ids, "inicio": solapado})
        assert r.status_code == 409, f"delta={delta} -> {r.status_code} {r.text}"
        assert r.status_code != 500


async def test_inicio_naive_se_asume_utc(client, seed_ids) -> None:
    naive = (datetime.now(timezone.utc) + timedelta(minutes=120)).replace(tzinfo=None).isoformat()
    r = await client.post("/api/turnos", json={**seed_ids, "inicio": naive})
    assert r.status_code == 201, r.text
    assert datetime.fromisoformat(r.json()["inicio"]).tzinfo is not None
