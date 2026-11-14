"""C-14 (3.3; D5; O13): nombres de tratamiento y sillón y matrículas únicos sin distinguir mayúsculas ni espacios.

Datos 100 % sintéticos (R19). Requiere PostgreSQL en localhost:5433.
"""

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.core import RegistroAuditoria
from app.turnos.models import Tratamiento

Factory = async_sessionmaker[AsyncSession]

NUEVO = {"duracion_minutos": 30, "precio_base": "5000.00"}


async def _auditorias(factory: Factory) -> int:
    async with factory() as s:
        return int((await s.execute(select(func.count()).select_from(RegistroAuditoria))).scalar_one())


async def test_un_nombre_nuevo_de_tratamiento_responde_201(client_recepcion: AsyncClient) -> None:
    r = await client_recepcion.post("/api/admin/tratamientos", json={"nombre": "Control de prueba", **NUEVO})
    assert r.status_code == 201, r.text


async def test_un_nombre_repetido_con_otras_mayusculas_y_espacios_responde_409_duplicado_con_el_campo_y_no_crea_nada(
        client_recepcion: AsyncClient, session_factory: Factory) -> None:
    await client_recepcion.post("/api/admin/tratamientos", json={"nombre": "Limpieza dental", **NUEVO})
    auditorias = await _auditorias(session_factory)
    r = await client_recepcion.post("/api/admin/tratamientos", json={"nombre": " limpieza DENTAL ", **NUEVO})
    assert r.status_code == 409, r.text
    assert (r.json()["motivo"], r.json()["campo"]) == ("duplicado", "nombre")
    async with session_factory() as s:
        assert (await s.execute(select(func.count()).select_from(Tratamiento))).scalar_one() == 1
    assert await _auditorias(session_factory) == auditorias


async def test_renombrar_un_sillon_al_mismo_nombre_responde_200_sin_error_de_duplicado(client_recepcion: AsyncClient) -> None:
    sillon = (await client_recepcion.post("/api/admin/sillones", json={"nombre": "Sillón 1"})).json()
    r = await client_recepcion.put(f"/api/admin/sillones/{sillon['id']}", json={"nombre": "Sillón 1"})
    assert r.status_code == 200, r.text
    r = await client_recepcion.put(f"/api/admin/sillones/{sillon['id']}", json={"nombre": "SILLÓN 1  "})
    assert r.status_code == 200, r.text  # cambiar solo las mayúsculas de uno mismo tampoco es un duplicado


async def test_renombrar_un_sillon_con_el_nombre_de_otro_responde_409_duplicado(client_recepcion: AsyncClient) -> None:
    await client_recepcion.post("/api/admin/sillones", json={"nombre": "Sillón 1"})
    segundo = (await client_recepcion.post("/api/admin/sillones", json={"nombre": "Sillón 2"})).json()
    r = await client_recepcion.put(f"/api/admin/sillones/{segundo['id']}", json={"nombre": "sillón 1"})
    assert r.status_code == 409 and (r.json()["motivo"], r.json()["campo"]) == ("duplicado", "nombre")
    assert (await client_recepcion.get(f"/api/admin/sillones/{segundo['id']}")).json()["nombre"] == "Sillón 2"


async def test_una_matricula_repetida_sin_distinguir_mayusculas_responde_409_duplicado_con_el_campo_matricula(
        client_recepcion: AsyncClient) -> None:
    await client_recepcion.post("/api/admin/profesionales", json={"nombre": "Dra. Ana Ficticia", "matricula": "MP-99001"})
    r = await client_recepcion.post("/api/admin/profesionales", json={"nombre": "Dr. Juan Ejemplo", "matricula": "mp-99001"})
    assert r.status_code == 409, r.text
    assert (r.json()["motivo"], r.json()["campo"]) == ("duplicado", "matricula")
    otra = await client_recepcion.post("/api/admin/profesionales", json={"nombre": "Dr. Juan Ejemplo", "matricula": "MP-99002"})
    assert otra.status_code == 201
    r = await client_recepcion.put(f"/api/admin/profesionales/{otra.json()['id']}", json={"matricula": " mp-99001"})
    assert r.status_code == 409 and r.json()["campo"] == "matricula"


async def test_dos_profesionales_pueden_llamarse_igual_si_la_matricula_difiere(client_recepcion: AsyncClient) -> None:
    await client_recepcion.post("/api/admin/profesionales", json={"nombre": "Dra. Ana Ficticia", "matricula": "MP-99001"})
    r = await client_recepcion.post("/api/admin/profesionales", json={"nombre": "Dra. Ana Ficticia", "matricula": "MP-99003"})
    assert r.status_code == 201


async def test_dos_altas_simultaneas_del_mismo_nombre_dan_un_201_y_un_409_nunca_un_500(client_recepcion: AsyncClient) -> None:
    import asyncio

    respuestas = await asyncio.gather(*[
        client_recepcion.post("/api/admin/tratamientos", json={"nombre": "Control de prueba", **NUEVO}) for _ in range(2)])
    assert sorted(r.status_code for r in respuestas) == [201, 409], [r.text for r in respuestas]
