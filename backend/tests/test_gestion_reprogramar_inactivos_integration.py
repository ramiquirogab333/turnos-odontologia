"""C-14 (5.5; D7): la reprogramación pública rechaza un profesional, tratamiento o sillón inactivo. Datos sintéticos (R19)."""

from datetime import timedelta

import pytest
from sqlalchemy import update

from app.turnos.models import Profesional, Sillon, Tratamiento
from tests.panel_helpers import LUNES, insertar_turno, local, sembrar_mundo, turno

URL = "/api/public/gestion/reprogramar"
AHORA = local(LUNES - timedelta(days=3), "12:00")


async def _preparar(session_factory, reloj):
    reloj(AHORA)
    mundo = await sembrar_mundo(session_factory)
    id_turno = await insertar_turno(session_factory, mundo, local(LUNES, "09:00"))
    codigo = str((await turno(session_factory, id_turno)).codigo_gestion)
    return mundo, id_turno, codigo


async def _reprogramar(client, codigo: str, hhmm: str = "11:00"):
    return await client.post(URL, json={"inicio": local(LUNES, hhmm).isoformat()}, headers={"X-Codigo-Gestion": codigo})


async def _poner(session_factory, modelo, id_, **valores) -> None:
    async with session_factory() as s:
        await s.execute(update(modelo).where(modelo.id == id_).values(**valores))
        await s.commit()


async def test_con_todo_activo_la_reprogramacion_sigue_funcionando(client, session_factory, reloj, notificador) -> None:
    _, id_turno, codigo = await _preparar(session_factory, reloj)
    r = await _reprogramar(client, codigo)
    assert r.status_code == 200, r.text
    assert (await turno(session_factory, id_turno)).inicio == local(LUNES, "11:00")


@pytest.mark.parametrize(("modelo", "clave", "campo"), [
    (Profesional, "ana", "profesional_id"),
    (Tratamiento, "trat", "tratamiento_id"),
])
async def test_un_profesional_o_tratamiento_inactivo_responde_422_no_reservable_y_el_turno_no_cambia(
        client, session_factory, reloj, notificador, modelo, clave, campo) -> None:
    mundo, id_turno, codigo = await _preparar(session_factory, reloj)
    antes = await turno(session_factory, id_turno)
    await _poner(session_factory, modelo, mundo[clave], is_active=False)
    r = await _reprogramar(client, codigo)
    assert r.status_code == 422, r.text
    assert (r.json()["motivo"], r.json()["campo"]) == ("no_reservable", campo)
    despues = await turno(session_factory, id_turno)
    assert (despues.inicio, despues.fin, despues.estado, despues.sillon_id) == (antes.inicio, antes.fin, antes.estado, antes.sillon_id)
    assert notificador.eventos == []


async def test_si_el_unico_sillon_pasa_a_mantenimiento_no_hay_horario_y_el_turno_no_cambia(
        client, session_factory, reloj, notificador) -> None:
    mundo, id_turno, codigo = await _preparar(session_factory, reloj)
    antes = await turno(session_factory, id_turno)
    await _poner(session_factory, Sillon, mundo["s1"], estado="mantenimiento")
    await _poner(session_factory, Sillon, mundo["s2"], estado="mantenimiento")
    r = await _reprogramar(client, codigo)
    assert r.status_code == 409, r.text  # sin sillón activo libre: conflicto con alternativas vacías, nunca 500
    assert (await turno(session_factory, id_turno)).inicio == antes.inicio
