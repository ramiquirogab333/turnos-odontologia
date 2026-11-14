"""C-14 (2.3, 3.3; D3, D4; O6): edición validada con lo guardado, FK inexistentes y franjas sin superposición.

Datos 100 % sintéticos (R19). Requiere PostgreSQL en localhost:5433.
"""

import asyncio
from datetime import time

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.core import Disponibilidad, RegistroAuditoria
from app.turnos.models import Profesional, Sillon

Factory = async_sessionmaker[AsyncSession]


async def _profesional(factory: Factory, nombre: str = "Dra. Ana Ficticia", matricula: str = "MP-99001") -> int:
    async with factory() as s:
        p = Profesional(nombre=nombre, matricula=matricula, especialidad="")
        s.add(p)
        await s.commit()
        return int(p.id)


async def _franja(client: AsyncClient, profesional_id: int, inicio: str, fin: str, dia: int = 0, **extra: object):
    return await client.post("/api/admin/disponibilidad", json={
        "profesional_id": profesional_id, "dia_semana": dia, "hora_inicio": inicio, "hora_fin": fin, **extra})


async def _cantidad(factory: Factory) -> int:
    async with factory() as s:
        return int((await s.execute(select(func.count()).select_from(Disponibilidad))).scalar_one())


async def _auditorias(factory: Factory) -> int:
    async with factory() as s:
        return int((await s.execute(select(func.count()).select_from(RegistroAuditoria))).scalar_one())


# --- 2.3 Edición validada con los valores guardados ------------------------------------------------------------------

async def test_cambiar_solo_el_fin_de_una_franja_responde_200_con_el_horario_nuevo(
        client_recepcion: AsyncClient, session_factory: Factory) -> None:
    ana = await _profesional(session_factory)
    franja = (await _franja(client_recepcion, ana, "09:00", "13:00")).json()
    r = await client_recepcion.put(f"/api/admin/disponibilidad/{franja['id']}", json={"hora_fin": "14:00"})
    assert r.status_code == 200, r.text
    assert (r.json()["hora_inicio"], r.json()["hora_fin"]) == ("09:00:00", "14:00:00")


async def test_un_fin_anterior_al_inicio_guardado_responde_422_nombrando_hora_fin_y_no_cambia_nada(
        client_recepcion: AsyncClient, session_factory: Factory) -> None:
    ana = await _profesional(session_factory)
    franja = (await _franja(client_recepcion, ana, "09:00", "13:00")).json()
    auditorias = await _auditorias(session_factory)
    r = await client_recepcion.put(f"/api/admin/disponibilidad/{franja['id']}", json={"hora_fin": "08:00"})
    assert r.status_code == 422, r.text
    assert r.json()["detail"][0]["loc"] == ["body", "hora_fin"]
    assert (await client_recepcion.get(f"/api/admin/disponibilidad/{franja['id']}")).json()["hora_fin"] == "13:00:00"
    assert await _auditorias(session_factory) == auditorias


async def test_un_inicio_igual_al_fin_guardado_responde_422(client_recepcion: AsyncClient, session_factory: Factory) -> None:
    ana = await _profesional(session_factory)
    franja = (await _franja(client_recepcion, ana, "09:00", "13:00")).json()
    r = await client_recepcion.put(f"/api/admin/disponibilidad/{franja['id']}", json={"hora_inicio": "13:00"})
    assert r.status_code == 422, r.text
    assert r.json()["detail"][0]["loc"] == ["body", "hora_inicio"]
    assert (await client_recepcion.get(f"/api/admin/disponibilidad/{franja['id']}")).json()["hora_inicio"] == "09:00:00"


async def test_editar_los_dos_extremos_a_la_vez_se_valida_con_los_valores_enviados(
        client_recepcion: AsyncClient, session_factory: Factory) -> None:
    ana = await _profesional(session_factory)
    franja = (await _franja(client_recepcion, ana, "09:00", "13:00")).json()
    r = await client_recepcion.put(f"/api/admin/disponibilidad/{franja['id']}", json={"hora_inicio": "15:00", "hora_fin": "18:00"})
    assert r.status_code == 200, r.text
    assert (r.json()["hora_inicio"], r.json()["hora_fin"]) == ("15:00:00", "18:00:00")


async def test_un_profesional_o_sillon_inexistente_responde_422_y_no_500(
        client_recepcion: AsyncClient, session_factory: Factory) -> None:
    ana = await _profesional(session_factory)
    assert (await _franja(client_recepcion, 999999, "09:00", "13:00")).status_code == 422
    r = await _franja(client_recepcion, ana, "09:00", "13:00", sillon_defecto_id=999999)
    assert r.status_code == 422, r.text
    assert "sillon_defecto_id" in r.json()["detail"]
    franja = (await _franja(client_recepcion, ana, "09:00", "13:00")).json()
    r = await client_recepcion.put(f"/api/admin/disponibilidad/{franja['id']}", json={"sillon_defecto_id": 999999})
    assert r.status_code == 422, r.text
    r = await client_recepcion.put(f"/api/admin/disponibilidad/{franja['id']}", json={"profesional_id": 999999})
    assert r.status_code == 422, r.text
    assert await _cantidad(session_factory) == 1


async def test_un_sillon_existente_como_preferido_se_acepta(client_recepcion: AsyncClient, session_factory: Factory) -> None:
    ana = await _profesional(session_factory)
    async with session_factory() as s:
        sillon = Sillon(nombre="Sillón 1", estado="activo")
        s.add(sillon)
        await s.commit()
        sillon_id = int(sillon.id)
    r = await _franja(client_recepcion, ana, "09:00", "13:00", sillon_defecto_id=sillon_id)
    assert r.status_code == 201 and r.json()["sillon_defecto_id"] == sillon_id


# --- 3.3 Franjas activas sin superposición ----------------------------------------------------------------------------

async def test_una_franja_de_otro_dia_o_de_otro_profesional_responde_201(
        client_recepcion: AsyncClient, session_factory: Factory) -> None:
    ana = await _profesional(session_factory)
    juan = await _profesional(session_factory, "Dr. Juan Ejemplo", "MP-99002")
    assert (await _franja(client_recepcion, ana, "09:00", "13:00")).status_code == 201
    assert (await _franja(client_recepcion, ana, "09:00", "13:00", dia=1)).status_code == 201
    assert (await _franja(client_recepcion, juan, "09:00", "13:00")).status_code == 201


async def test_una_franja_superpuesta_responde_409_con_el_id_y_el_horario_de_la_que_choca_y_no_crea_nada(
        client_recepcion: AsyncClient, session_factory: Factory) -> None:
    ana = await _profesional(session_factory)
    existente = (await _franja(client_recepcion, ana, "09:00", "13:00")).json()
    auditorias = await _auditorias(session_factory)
    r = await _franja(client_recepcion, ana, "12:00", "15:00")
    assert r.status_code == 409, r.text
    cuerpo = r.json()
    assert cuerpo["motivo"] == "franja_superpuesta"
    assert cuerpo["franja"] == {"id": existente["id"], "dia_semana": 0, "hora_inicio": "09:00:00", "hora_fin": "13:00:00"}
    assert await _cantidad(session_factory) == 1
    assert await _auditorias(session_factory) == auditorias


async def test_las_franjas_contiguas_se_aceptan(client_recepcion: AsyncClient, session_factory: Factory) -> None:
    ana = await _profesional(session_factory)
    assert (await _franja(client_recepcion, ana, "09:00", "13:00")).status_code == 201
    assert (await _franja(client_recepcion, ana, "13:00", "17:00")).status_code == 201


async def test_una_franja_pausada_no_cuenta_para_la_superposicion_pero_al_reactivarla_se_rechaza(
        client_recepcion: AsyncClient, session_factory: Factory) -> None:
    ana = await _profesional(session_factory)
    await _franja(client_recepcion, ana, "09:00", "13:00")
    pausada = await _franja(client_recepcion, ana, "12:00", "15:00", activo=False)
    assert pausada.status_code == 201, pausada.text
    r = await client_recepcion.put(f"/api/admin/disponibilidad/{pausada.json()['id']}", json={"activo": True})
    assert r.status_code == 409 and r.json()["motivo"] == "franja_superpuesta"
    assert (await client_recepcion.get(f"/api/admin/disponibilidad/{pausada.json()['id']}")).json()["activo"] is False


async def test_editar_una_franja_hasta_pisar_a_otra_responde_409_y_queda_como_estaba(
        client_recepcion: AsyncClient, session_factory: Factory) -> None:
    ana = await _profesional(session_factory)
    await _franja(client_recepcion, ana, "09:00", "13:00")
    tarde = (await _franja(client_recepcion, ana, "13:00", "17:00")).json()
    r = await client_recepcion.put(f"/api/admin/disponibilidad/{tarde['id']}", json={"hora_inicio": "12:00"})
    assert r.status_code == 409 and r.json()["motivo"] == "franja_superpuesta"
    assert (await client_recepcion.get(f"/api/admin/disponibilidad/{tarde['id']}")).json()["hora_inicio"] == "13:00:00"


async def test_editar_una_franja_sin_pisar_a_nadie_no_choca_consigo_misma(
        client_recepcion: AsyncClient, session_factory: Factory) -> None:
    ana = await _profesional(session_factory)
    franja = (await _franja(client_recepcion, ana, "09:00", "13:00")).json()
    r = await client_recepcion.put(f"/api/admin/disponibilidad/{franja['id']}", json={"hora_fin": "12:00"})
    assert r.status_code == 200, r.text


async def test_dos_altas_superpuestas_al_mismo_tiempo_dan_un_201_y_un_409_nunca_un_500(
        client_recepcion: AsyncClient, session_factory: Factory) -> None:
    ana = await _profesional(session_factory)
    respuestas = await asyncio.gather(
        _franja(client_recepcion, ana, "10:00", "12:00"),
        _franja(client_recepcion, ana, "11:00", "14:00"),
    )
    assert sorted(r.status_code for r in respuestas) == [201, 409], [r.text for r in respuestas]
    perdedora = next(r for r in respuestas if r.status_code == 409)
    assert perdedora.json()["motivo"] == "franja_superpuesta"
    async with session_factory() as s:
        assert (await s.execute(select(func.count()).select_from(Disponibilidad)
                                .where(Disponibilidad.is_active.is_(True)))).scalar_one() == 1
    assert time(10) < time(11)  # las horas de la prueba son ordenables (sanidad del escenario)
