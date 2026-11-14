"""C-14 (5.3; D7): el alta manual y las opciones de la agenda frente a ítems inactivos. Datos 100 % sintéticos (R19)."""

import pytest
from sqlalchemy import func, select, update

from app.models.core import RegistroAuditoria
from app.turnos.models import Profesional, Sillon, Tratamiento, Turno
from tests.conftest import bearer, crear_usuario_panel
from tests.panel_helpers import LUNES, cuerpo_alta, insertar_turno, local, sembrar_mundo

URL = "/api/panel/turnos"
AHORA = local(LUNES, "07:00")


@pytest.fixture
async def mundo(session_factory, clean_db):
    return await sembrar_mundo(session_factory, duracion=45)


@pytest.fixture
async def rec(session_factory, mundo, reloj):
    reloj(AHORA)
    usuario_id, token = await crear_usuario_panel(session_factory, "recepcion@turnos.test", ["recepcion"])
    return {"id": usuario_id, "cab": bearer(token)}


async def _contar(session_factory, modelo) -> int:
    async with session_factory() as s:
        return int((await s.execute(select(func.count()).select_from(modelo))).scalar_one())


async def _poner(session_factory, modelo, id_, **valores) -> None:
    async with session_factory() as s:
        await s.execute(update(modelo).where(modelo.id == id_).values(**valores))
        await s.commit()


async def test_el_alta_con_items_activos_responde_201_como_siempre(client, session_factory, mundo, rec) -> None:
    r = await client.post(URL, json=cuerpo_alta(mundo, local(LUNES, "10:00")), headers=rec["cab"])
    assert r.status_code == 201, r.text


async def test_el_alta_con_un_profesional_inactivo_responde_422_no_reservable_y_no_crea_turno_ni_auditoria(
        client, session_factory, mundo, rec) -> None:
    await _poner(session_factory, Profesional, mundo["ana"], is_active=False)
    auditorias = await _contar(session_factory, RegistroAuditoria)
    r = await client.post(URL, json=cuerpo_alta(mundo, local(LUNES, "10:00")), headers=rec["cab"])
    assert r.status_code == 422, r.text
    assert (r.json()["motivo"], r.json()["campo"]) == ("no_reservable", "profesional_id")
    assert await _contar(session_factory, Turno) == 0
    assert await _contar(session_factory, RegistroAuditoria) == auditorias


async def test_el_alta_con_un_tratamiento_inactivo_responde_422_no_reservable_con_el_campo(client, session_factory, mundo, rec) -> None:
    await _poner(session_factory, Tratamiento, mundo["trat"], is_active=False)
    r = await client.post(URL, json=cuerpo_alta(mundo, local(LUNES, "10:00")), headers=rec["cab"])
    assert r.status_code == 422, r.text
    assert (r.json()["motivo"], r.json()["campo"]) == ("no_reservable", "tratamiento_id")
    assert await _contar(session_factory, Turno) == 0


@pytest.mark.parametrize("estado", ["mantenimiento", "inactivo"])
async def test_el_alta_con_un_sillon_elegido_que_no_esta_activo_responde_422_no_reservable_con_campo_sillon_id(
        client, session_factory, mundo, rec, estado) -> None:
    await _poner(session_factory, Sillon, mundo["s2"], estado=estado)
    r = await client.post(URL, json=cuerpo_alta(mundo, local(LUNES, "10:00"), sillon_id=mundo["s2"]), headers=rec["cab"])
    assert r.status_code == 422, r.text
    assert (r.json()["motivo"], r.json()["campo"]) == ("no_reservable", "sillon_id")
    assert await _contar(session_factory, Turno) == 0


async def test_un_sillon_elegido_que_si_esta_activo_se_acepta(client, session_factory, mundo, rec) -> None:
    r = await client.post(URL, json=cuerpo_alta(mundo, local(LUNES, "10:00"), sillon_id=mundo["s2"]), headers=rec["cab"])
    assert r.status_code == 201, r.text
    assert r.json()["sillon_id"] == mundo["s2"]


async def test_las_opciones_de_la_agenda_informan_activo_en_profesionales_y_tratamientos_y_sillones_solo_activos(
        client, session_factory, mundo, rec) -> None:
    await _poner(session_factory, Profesional, mundo["bruno"], is_active=False)
    await _poner(session_factory, Sillon, mundo["s2"], estado="mantenimiento")
    r = await client.get("/api/panel/agenda/opciones", headers=rec["cab"])
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert {p["nombre"]: p["activo"] for p in cuerpo["profesionales"]} == {"Dra. Ana Ficticia": True, "Dr. Bruno Ejemplo": False}
    assert [(t["nombre"], t["activo"]) for t in cuerpo["tratamientos"]] == [("Limpieza dental", True)]
    assert [s["nombre"] for s in cuerpo["sillones"]] == ["Sillón 1"]


async def test_filtrar_la_agenda_por_un_profesional_inactivo_sigue_mostrando_sus_turnos(client, session_factory, mundo, rec) -> None:
    for hhmm in ("09:00", "10:00"):
        await insertar_turno(session_factory, mundo, local(LUNES, hhmm), prof="bruno", sillon="s2")
    await _poner(session_factory, Profesional, mundo["bruno"], is_active=False)
    r = await client.get("/api/panel/agenda", params={"vista": "dia", "fecha": LUNES.isoformat(),
                                                      "profesional_id": mundo["bruno"]}, headers=rec["cab"])
    assert r.status_code == 200, r.text
    assert len(r.json()["turnos"]) == 2
