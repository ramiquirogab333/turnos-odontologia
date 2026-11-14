"""C-14 (3.1, 3.2; D1, D3, D10; O1, O7): baja lógica, auditoría de ``activo`` y borrado con 409 ``en_uso``.

Datos 100 % sintéticos (R19). Requiere PostgreSQL en localhost:5433.
"""

from datetime import datetime, time, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.core import Disponibilidad, RegistroAuditoria
from app.turnos.models import Profesional, Sillon, Tratamiento, Turno
from tests.clinica_helpers import crear_paciente
from tests.gcal_helpers import sembrar_conexion
from tests.panel_helpers import insertar_turno, local, sembrar_mundo, LUNES
from tests.presupuestos_helpers import crear_presupuesto

Factory = async_sessionmaker[AsyncSession]


async def _auditorias(factory: Factory, entidad: str | None = None) -> list[RegistroAuditoria]:
    async with factory() as s:
        consulta = select(RegistroAuditoria).order_by(RegistroAuditoria.id)
        if entidad is not None:
            consulta = consulta.where(RegistroAuditoria.entidad == entidad)
        return list((await s.execute(consulta)).scalars())


async def _contar(factory: Factory, modelo: type) -> int:
    async with factory() as s:
        return int((await s.execute(select(func.count()).select_from(modelo))).scalar_one())


PASADO = datetime(2024, 3, 4, 10, 0, tzinfo=timezone.utc)


# --- Baja lógica (D1, D10) -------------------------------------------------------------------------------------------

async def test_desactivar_un_tratamiento_con_turnos_pasados_responde_200_lo_conserva_y_audita_antes_y_despues_con_la_ip(
        client_recepcion: AsyncClient, session_factory: Factory) -> None:
    mundo = await sembrar_mundo(session_factory)
    await insertar_turno(session_factory, mundo, PASADO, estado="atendido")
    r = await client_recepcion.put(f"/api/admin/tratamientos/{mundo['trat']}", json={"activo": False})
    assert r.status_code == 200, r.text
    assert r.json()["activo"] is False
    listado = (await client_recepcion.get("/api/admin/tratamientos")).json()
    assert [(t["id"], t["activo"]) for t in listado] == [(mundo["trat"], False)]
    update = [a for a in await _auditorias(session_factory, "tratamiento") if a.accion == "UPDATE"]
    assert len(update) == 1
    assert update[0].datos_antes["is_active"] is True and update[0].datos_despues["is_active"] is False
    assert update[0].datos_despues["campos"] == ["is_active"]
    assert update[0].ip is not None


async def test_el_alta_de_un_tratamiento_nace_activo_y_se_puede_dar_de_alta_inactivo(client_recepcion: AsyncClient) -> None:
    nuevo = {"nombre": "Limpieza sintética", "duracion_minutos": 30, "precio_base": "5000.00"}
    r = await client_recepcion.post("/api/admin/tratamientos", json=nuevo)
    assert r.status_code == 201 and r.json()["activo"] is True
    r = await client_recepcion.post("/api/admin/tratamientos", json={**nuevo, "nombre": "Control sintético", "activo": False})
    assert r.status_code == 201 and r.json()["activo"] is False


async def test_un_activo_invalido_responde_422_y_no_cambia_ni_audita_nada(
        client_recepcion: AsyncClient, session_factory: Factory) -> None:
    mundo = await sembrar_mundo(session_factory)
    antes = len(await _auditorias(session_factory))
    r = await client_recepcion.put(f"/api/admin/profesionales/{mundo['ana']}", json={"activo": "quizas"})
    assert r.status_code == 422
    assert (await client_recepcion.get(f"/api/admin/profesionales/{mundo['ana']}")).json()["activo"] is True
    assert len(await _auditorias(session_factory)) == antes


async def test_reactivar_una_franja_pausada_sin_conflicto_responde_200_y_vuelve_a_estar_activa(
        client_recepcion: AsyncClient, session_factory: Factory) -> None:
    mundo = await sembrar_mundo(session_factory)
    async with session_factory() as s:
        s.add(Disponibilidad(profesional_id=mundo["ana"], dia_semana=0, hora_inicio=time(14), hora_fin=time(18), is_active=False))
        await s.commit()
        pausada = (await s.execute(select(Disponibilidad.id).where(Disponibilidad.is_active.is_(False)))).scalar_one()
    r = await client_recepcion.put(f"/api/admin/disponibilidad/{pausada}", json={"activo": True})
    assert r.status_code == 200, r.text
    assert r.json()["activo"] is True


async def test_pausar_una_franja_la_conserva_con_activo_falso_en_la_lectura(
        client_recepcion: AsyncClient, session_factory: Factory) -> None:
    mundo = await sembrar_mundo(session_factory)
    franja = (await client_recepcion.get("/api/admin/disponibilidad")).json()[0]
    r = await client_recepcion.put(f"/api/admin/disponibilidad/{franja['id']}", json={"activo": False})
    assert r.status_code == 200 and r.json()["activo"] is False
    assert (await client_recepcion.get(f"/api/admin/disponibilidad/{franja['id']}")).json()["activo"] is False
    assert mundo["ana"] == franja["profesional_id"] or mundo["bruno"] == franja["profesional_id"]


# --- Borrar un ítem en uso responde 409 (D1) ---------------------------------------------------------------------------

async def test_borrar_un_sillon_sin_uso_responde_204_y_se_audita(client_recepcion: AsyncClient, session_factory: Factory) -> None:
    async with session_factory() as s:
        sillon = Sillon(nombre="Sillón de prueba", estado="activo")
        s.add(sillon)
        await s.commit()
        sillon_id = int(sillon.id)
    r = await client_recepcion.delete(f"/api/admin/sillones/{sillon_id}")
    assert r.status_code == 204
    assert [a.accion for a in await _auditorias(session_factory, "sillon")] == ["DELETE"]
    assert (await client_recepcion.get(f"/api/admin/sillones/{sillon_id}")).status_code == 404


async def test_borrar_un_profesional_con_un_turno_cancelado_responde_409_en_uso_sin_borrar_nada_ni_auditar(
        client_recepcion: AsyncClient, session_factory: Factory) -> None:
    mundo = await sembrar_mundo(session_factory)
    await insertar_turno(session_factory, mundo, PASADO, estado="cancelado")
    antes = len(await _auditorias(session_factory))
    franjas = await _contar(session_factory, Disponibilidad)
    r = await client_recepcion.delete(f"/api/admin/profesionales/{mundo['ana']}")
    assert r.status_code == 409, r.text
    assert r.json()["motivo"] == "en_uso"
    assert "desactiv" in r.json()["detail"].lower()
    assert (await client_recepcion.get(f"/api/admin/profesionales/{mundo['ana']}")).status_code == 200
    assert await _contar(session_factory, Disponibilidad) == franjas  # sus franjas siguen
    assert len(await _auditorias(session_factory)) == antes


async def test_borrar_un_profesional_sin_turnos_arrastra_sus_franjas_y_audita_un_solo_delete(
        client_recepcion: AsyncClient, session_factory: Factory) -> None:
    mundo = await sembrar_mundo(session_factory)
    r = await client_recepcion.delete(f"/api/admin/profesionales/{mundo['bruno']}")
    assert r.status_code == 204, r.text
    assert await _contar(session_factory, Disponibilidad) == 7  # quedan las de la otra profesional
    assert [a.accion for a in await _auditorias(session_factory, "profesional")] == ["DELETE"]
    assert await _auditorias(session_factory, "disponibilidad") == []


async def test_borrar_un_tratamiento_o_un_sillon_con_turnos_responde_409_en_uso(
        client_recepcion: AsyncClient, session_factory: Factory) -> None:
    mundo = await sembrar_mundo(session_factory)
    await insertar_turno(session_factory, mundo, PASADO, estado="atendido")
    for ruta in (f"/api/admin/tratamientos/{mundo['trat']}", f"/api/admin/sillones/{mundo['s1']}"):
        r = await client_recepcion.delete(ruta)
        assert r.status_code == 409 and r.json()["motivo"] == "en_uso", ruta
    # el sillón sin turnos sí se puede borrar
    assert (await client_recepcion.delete(f"/api/admin/sillones/{mundo['s2']}")).status_code == 204


async def test_borrar_un_tratamiento_con_lineas_de_presupuesto_responde_409_en_uso(
        client_recepcion: AsyncClient, session_factory: Factory, token_recepcion: str) -> None:
    mundo = await sembrar_mundo(session_factory)
    paciente = await crear_paciente(session_factory)
    creado = await crear_presupuesto(client_recepcion, token_recepcion, paciente, (mundo["trat"], 1))
    assert creado.status_code == 201, creado.text
    r = await client_recepcion.delete(f"/api/admin/tratamientos/{mundo['trat']}")
    assert r.status_code == 409 and r.json()["motivo"] == "en_uso"


async def test_borrar_un_profesional_con_conexion_de_calendario_responde_409_en_uso(
        client_recepcion: AsyncClient, session_factory: Factory) -> None:
    mundo = await sembrar_mundo(session_factory)
    await sembrar_conexion(session_factory, mundo["ana"])
    r = await client_recepcion.delete(f"/api/admin/profesionales/{mundo['ana']}")
    assert r.status_code == 409 and r.json()["motivo"] == "en_uso"


async def test_borrar_una_franja_con_turnos_futuros_responde_204_y_los_turnos_siguen_intactos_y_se_audita(
        client_recepcion: AsyncClient, session_factory: Factory) -> None:
    mundo = await sembrar_mundo(session_factory, franja=("14:00", "18:00"))
    ids = [await insertar_turno(session_factory, mundo, local(LUNES, hhmm)) for hhmm in ("14:00", "15:00", "16:00")]
    franja = next(f for f in (await client_recepcion.get("/api/admin/disponibilidad")).json()
                  if f["profesional_id"] == mundo["ana"] and f["dia_semana"] == 0)
    r = await client_recepcion.delete(f"/api/admin/disponibilidad/{franja['id']}")
    assert r.status_code == 204, r.text
    async with session_factory() as s:
        turnos = list((await s.execute(select(Turno).where(Turno.id.in_(ids)).order_by(Turno.id))).scalars())
    assert [t.estado for t in turnos] == ["reservado"] * 3
    assert [t.inicio for t in turnos] == [local(LUNES, hhmm) for hhmm in ("14:00", "15:00", "16:00")]
    assert [a.accion for a in await _auditorias(session_factory, "disponibilidad")] == ["DELETE"]


async def test_borrar_un_id_inexistente_responde_404_y_no_audita(client_recepcion: AsyncClient, session_factory: Factory) -> None:
    for recurso in ("tratamientos", "profesionales", "sillones", "disponibilidad"):
        assert (await client_recepcion.delete(f"/api/admin/{recurso}/999999")).status_code == 404
    assert await _auditorias(session_factory) == []


async def test_un_update_con_null_explicito_en_un_campo_obligatorio_responde_422_y_no_500(
        client_recepcion: AsyncClient, session_factory: Factory) -> None:
    mundo = await sembrar_mundo(session_factory)
    r = await client_recepcion.put(f"/api/admin/tratamientos/{mundo['trat']}", json={"duracion_minutos": None})
    assert r.status_code == 422, r.text
    assert (await client_recepcion.get(f"/api/admin/tratamientos/{mundo['trat']}")).json()["duracion_minutos"] == 30
    assert datetime.now(timezone.utc) - timedelta(days=1) < datetime.now(timezone.utc)  # reloj sano


async def test_un_profesional_y_un_tratamiento_inactivos_siguen_visibles_en_el_admin(
        client_recepcion: AsyncClient, session_factory: Factory) -> None:
    mundo = await sembrar_mundo(session_factory)
    async with session_factory() as s:
        for modelo, id_ in ((Profesional, mundo["bruno"]), (Tratamiento, mundo["trat"])):
            fila = await s.get(modelo, id_)
            assert fila is not None
            fila.is_active = False
        await s.commit()
    profesionales = (await client_recepcion.get("/api/admin/profesionales")).json()
    assert {p["nombre"]: p["activo"] for p in profesionales} == {"Dra. Ana Ficticia": True, "Dr. Bruno Ejemplo": False}
    assert (await client_recepcion.get("/api/admin/tratamientos")).json()[0]["activo"] is False
