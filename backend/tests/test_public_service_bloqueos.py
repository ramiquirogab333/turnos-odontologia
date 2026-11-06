"""C-07 (4.1): ``_cargar_bloqueos`` puede excluir un turno (el propio al reprogramar). Datos sintéticos (R19)."""

import uuid
from datetime import timedelta

from app.public.service import _cargar_bloqueos
from app.turnos.models import Turno
from tests.sena_helpers import fecha_laboral, local


async def _turno(factory, ids, inicio, estado="reservado") -> int:
    async with factory() as s:
        t = Turno(profesional_id=ids["profesional_id"], sillon_id=ids["sillon_id"],
                  tratamiento_id=ids["tratamiento_id"], paciente_id=None, inicio=inicio,
                  fin=inicio + timedelta(minutes=30), estado=estado, codigo_gestion=str(uuid.uuid4()),
                  contacto_nombre="Carlos Sintético", contacto_telefono="+5491144445555")
        s.add(t)
        await s.flush()
        await s.commit()
        return int(t.id)


async def test_sin_el_parametro_devuelve_todos_los_bloqueantes(session_factory, seed_ids) -> None:
    f = fecha_laboral()
    a = await _turno(session_factory, seed_ids, local(f, "10:00"))
    await _turno(session_factory, seed_ids, local(f, "11:00"))
    await _turno(session_factory, seed_ids, local(f, "10:00"), estado="cancelado")  # no bloquea
    async with session_factory() as s:
        bloqueos = await _cargar_bloqueos(s, local(f, "09:00"), local(f, "12:00"))
    assert sorted(b.inicio for b in bloqueos) == [local(f, "10:00"), local(f, "11:00")]
    assert a  # el turno existe


async def test_excluir_turno_id_saca_solo_ese_turno(session_factory, seed_ids) -> None:
    f = fecha_laboral()
    a = await _turno(session_factory, seed_ids, local(f, "10:00"))
    await _turno(session_factory, seed_ids, local(f, "11:00"))
    async with session_factory() as s:
        bloqueos = await _cargar_bloqueos(s, local(f, "09:00"), local(f, "12:00"), excluir_turno_id=a)
    assert [b.inicio for b in bloqueos] == [local(f, "11:00")]


async def test_excluir_un_id_inexistente_no_cambia_el_resultado(session_factory, seed_ids) -> None:
    f = fecha_laboral()
    await _turno(session_factory, seed_ids, local(f, "10:00"))
    async with session_factory() as s:
        con = await _cargar_bloqueos(s, local(f, "09:00"), local(f, "12:00"), excluir_turno_id=999999)
        sin = await _cargar_bloqueos(s, local(f, "09:00"), local(f, "12:00"))
    assert con == sin and len(con) == 1
