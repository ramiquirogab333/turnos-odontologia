"""C-14 (5.1; D7, D8; O1): lo inactivo no se ofrece ni se reserva en la reserva pública. Datos 100 % sintéticos (R19)."""

from datetime import time

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.core import Disponibilidad
from app.pagos.models import PagoSena
from app.turnos.models import Profesional, Sillon, Tratamiento, Turno
from tests.panel_helpers import LUNES, local, sembrar_mundo

Factory = async_sessionmaker[AsyncSession]


async def _activo(factory: Factory, modelo: type, id_: int, valor: bool) -> None:
    async with factory() as s:
        await s.execute(update(modelo).where(modelo.id == id_).values(is_active=valor))  # type: ignore[attr-defined]
        await s.commit()


async def _disponibilidad(client: AsyncClient, mundo: dict[str, int], profesional: str = "ana"):
    return await client.get("/api/public/disponibilidad", params={
        "profesional_id": mundo[profesional], "tratamiento_id": mundo["trat"],
        "desde": LUNES.isoformat(), "hasta": LUNES.isoformat()})


async def _reservar(client: AsyncClient, mundo: dict[str, int], **extra: object):
    cuerpo = {"nombre": "Carlos Sintético", "telefono": "+5491144445555", "tratamiento_id": mundo["trat"],
              "profesional_id": mundo["ana"], "inicio": local(LUNES, "10:00").isoformat(), **extra}
    return await client.post("/api/public/turnos", json=cuerpo)


async def _contar(factory: Factory, modelo: type) -> int:
    async with factory() as s:
        return int((await s.execute(select(func.count()).select_from(modelo))).scalar_one())


async def test_un_tratamiento_inactivo_no_figura_en_el_listado_publico_y_no_se_expone_el_campo_activo(
        client: AsyncClient, session_factory: Factory) -> None:
    mundo = await sembrar_mundo(session_factory)
    async with session_factory() as s:
        s.add(Tratamiento(nombre="Ortodoncia demo", duracion_minutos=60, precio_base=1000, is_active=False))
        await s.commit()
    r = await client.get("/api/public/tratamientos")
    assert r.status_code == 200
    assert [t["nombre"] for t in r.json()] == ["Limpieza dental"]
    assert all("activo" not in t and "is_active" not in t for t in r.json())
    await _activo(session_factory, Tratamiento, mundo["trat"], False)
    assert (await client.get("/api/public/tratamientos")).json() == []  # todo inactivo: lista vacía, 200


async def test_un_profesional_inactivo_con_franja_activa_no_figura_pero_el_activo_con_franja_si(
        client: AsyncClient, session_factory: Factory) -> None:
    mundo = await sembrar_mundo(session_factory)
    await _activo(session_factory, Profesional, mundo["bruno"], False)
    r = await client.get("/api/public/profesionales")
    assert r.status_code == 200
    assert [p["nombre"] for p in r.json()] == ["Dra. Ana Ficticia"]
    assert all("matricula" not in p and "activo" not in p for p in r.json())


async def test_la_disponibilidad_con_un_tratamiento_o_profesional_inactivo_responde_422_no_reservable_con_el_campo(
        client: AsyncClient, session_factory: Factory) -> None:
    mundo = await sembrar_mundo(session_factory)
    await _activo(session_factory, Tratamiento, mundo["trat"], False)
    r = await _disponibilidad(client, mundo)
    assert r.status_code == 422, r.text
    assert (r.json()["motivo"], r.json()["campo"]) == ("no_reservable", "tratamiento_id")
    await _activo(session_factory, Tratamiento, mundo["trat"], True)
    await _activo(session_factory, Profesional, mundo["ana"], False)
    r = await _disponibilidad(client, mundo)
    assert r.status_code == 422 and (r.json()["motivo"], r.json()["campo"]) == ("no_reservable", "profesional_id")


async def test_reservar_un_tratamiento_desactivado_mientras_el_paciente_elegia_responde_422_y_no_crea_turno_ni_pago(
        client: AsyncClient, session_factory: Factory) -> None:
    mundo = await sembrar_mundo(session_factory)
    await _activo(session_factory, Tratamiento, mundo["trat"], False)
    r = await _reservar(client, mundo)
    assert r.status_code == 422, r.text
    assert (r.json()["motivo"], r.json()["campo"]) == ("no_reservable", "tratamiento_id")
    assert (await _contar(session_factory, Turno), await _contar(session_factory, PagoSena)) == (0, 0)


async def test_reservar_con_un_profesional_inactivo_responde_422_no_reservable_y_no_crea_nada(
        client: AsyncClient, session_factory: Factory) -> None:
    mundo = await sembrar_mundo(session_factory)
    await _activo(session_factory, Profesional, mundo["ana"], False)
    r = await _reservar(client, mundo)
    assert r.status_code == 422, r.text
    assert (r.json()["motivo"], r.json()["campo"]) == ("no_reservable", "profesional_id")
    assert await _contar(session_factory, Turno) == 0


async def test_un_id_inexistente_sigue_siendo_referencia_inexistente_y_no_no_reservable(
        client: AsyncClient, session_factory: Factory) -> None:
    mundo = await sembrar_mundo(session_factory)
    r = await _reservar(client, mundo, tratamiento_id=999999)
    assert r.status_code == 422 and "motivo" not in r.json()


async def test_al_reactivar_el_tratamiento_vuelven_a_ofrecerse_horarios_sin_otro_paso(
        client: AsyncClient, session_factory: Factory) -> None:
    mundo = await sembrar_mundo(session_factory)
    await _activo(session_factory, Tratamiento, mundo["trat"], False)
    assert (await _disponibilidad(client, mundo)).status_code == 422
    await _activo(session_factory, Tratamiento, mundo["trat"], True)
    r = await _disponibilidad(client, mundo)
    assert r.status_code == 200 and r.json()["slots"]
    assert (await _reservar(client, mundo)).status_code == 201


@pytest.mark.parametrize("estado", ["mantenimiento", "inactivo"])
async def test_si_el_unico_sillon_activo_pasa_a_mantenimiento_o_fuera_de_uso_la_lista_de_horarios_queda_vacia_con_200(
        client: AsyncClient, session_factory: Factory, estado: str) -> None:
    mundo = await sembrar_mundo(session_factory)
    async with session_factory() as s:
        await s.execute(update(Sillon).where(Sillon.id == mundo["s2"]).values(estado="inactivo"))
        await s.execute(update(Sillon).where(Sillon.id == mundo["s1"]).values(estado=estado))
        await s.commit()
    r = await _disponibilidad(client, mundo)
    assert r.status_code == 200, r.text
    assert r.json()["slots"] == []


async def test_un_profesional_activo_cuyas_franjas_estan_pausadas_no_se_lista(client: AsyncClient, session_factory: Factory) -> None:
    mundo = await sembrar_mundo(session_factory)
    async with session_factory() as s:
        await s.execute(update(Disponibilidad).where(Disponibilidad.profesional_id == mundo["bruno"]).values(is_active=False))
        await s.commit()
    assert [p["nombre"] for p in (await client.get("/api/public/profesionales")).json()] == ["Dra. Ana Ficticia"]
    assert time(9) < time(13)
