"""C-12 (grupo 5): deshacer un ``atendido`` marcado por error. Datos sintéticos (R19)."""

import asyncio
from datetime import date, datetime, timedelta

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select

from app.models.core import RegistroAuditoria
from app.pagos.models import PagoSena
from tests.caja_helpers import en, sena
from tests.clinica_helpers import AHORA, Escenario, auditorias, sembrar_escenario
from tests.conftest import NotificadorEspia, bearer
from tests.panel_helpers import cuerpo_alta, insertar_turno, local, turno

DIA = date(2026, 11, 10)  # martes; AHORA = 2026-11-10 12:00 UTC = 09:00 en la clínica


@pytest.fixture
async def esc(session_factory, reloj) -> Escenario:  # type: ignore[no-untyped-def]
    reloj(AHORA)
    return await sembrar_escenario(session_factory)


async def deshacer(client: AsyncClient, token: str, turno_id: int, motivo: str = "paciente_no_asistio") -> Response:
    return await client.post(f"/api/panel/turnos/{turno_id}/deshacer-atendido", json={"motivo": motivo},
                             headers=bearer(token))


async def atendido(factory, esc: Escenario, inicio: datetime, *, con_sena: bool = True, prof: str = "ana") -> int:  # type: ignore[no-untyped-def]
    if con_sena:
        turno_id, _ = await sena(factory, esc, acreditado_en=inicio - timedelta(days=3), turno_estado="atendido",
                                 inicio=inicio)
        return turno_id
    return await insertar_turno(factory, esc.mundo, inicio, estado="atendido", prof=prof,
                                sillon="s1" if prof == "ana" else "s2", origen="manual")


async def pago_estado(factory, turno_id: int) -> str:  # type: ignore[no-untyped-def]
    async with factory() as s:
        return (await s.execute(select(PagoSena.estado).where(PagoSena.turno_id == turno_id))).scalar_one()


# --- 5.3 Deshacer un atendido marcado por error ------------------------------------------------------------------

async def test_recepcion_deshace_un_atendido_y_el_turno_vuelve_a_reservado_con_su_sena_y_su_horario(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    inicio = local(DIA, "11:00")  # hoy, dentro de la franja 09-13; ya fue marcado atendido antes de su hora
    turno_id = await atendido(session_factory, esc, inicio)
    r = await deshacer(client, esc.recepcion, turno_id)
    assert r.status_code == 200, r.text
    assert (r.json()["turno_id"], r.json()["estado"], r.json()["estado_sena"]) == (turno_id, "reservado", "acreditado")
    assert (await turno(session_factory, turno_id)).estado == "reservado"
    assert await pago_estado(session_factory, turno_id) == "acreditado"
    solapado = await client.post("/api/panel/turnos", json=cuerpo_alta(esc.mundo, local(DIA, "11:00")),
                                 headers=bearer(esc.recepcion))
    assert solapado.status_code == 409  # el horario sigue ocupado (R5)


async def test_admin_tambien_puede_y_un_atendido_sin_sena_vuelve_con_estado_sena_nulo(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    turno_id = await atendido(session_factory, esc, local(DIA, "10:00"), con_sena=False)
    r = await deshacer(client, esc.admin, turno_id, "turno_equivocado")
    assert r.status_code == 200 and r.json()["estado"] == "reservado" and r.json()["estado_sena"] is None


@pytest.mark.parametrize("estado", ["ausente", "cancelado", "reservado", "confirmado"])
async def test_un_turno_que_no_esta_atendido_da_409_transicion_invalida_y_no_cambia(session_factory, client: AsyncClient, esc, estado: str) -> None:  # type: ignore[no-untyped-def]
    turno_id = await insertar_turno(session_factory, esc.mundo, local(DIA, "10:00"), estado=estado, origen="manual")
    r = await deshacer(client, esc.recepcion, turno_id)
    assert r.status_code == 409 and r.json()["motivo"] == "transicion_invalida"
    assert (await turno(session_factory, turno_id)).estado == estado


async def test_la_odontologa_recibe_403_incluso_sobre_su_propio_turno_atendido(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    turno_id = await atendido(session_factory, esc, local(DIA, "10:00"), con_sena=False)
    assert (await deshacer(client, esc.ana, turno_id)).status_code == 403
    assert (await client.post(f"/api/panel/turnos/{turno_id}/deshacer-atendido", json={"motivo": "otro"})).status_code == 401
    assert (await turno(session_factory, turno_id)).estado == "atendido"


@pytest.mark.parametrize("cuerpo", [{"motivo": "porque sí"}, {}, {"motivo": ""}, {"motivo": "otro", "x": 1}])
async def test_un_motivo_fuera_del_catalogo_o_faltante_da_422_y_el_turno_sigue_atendido(session_factory, client: AsyncClient, esc, cuerpo: dict[str, object]) -> None:  # type: ignore[no-untyped-def]
    turno_id = await atendido(session_factory, esc, local(DIA, "10:00"), con_sena=False)
    r = await client.post(f"/api/panel/turnos/{turno_id}/deshacer-atendido", json=cuerpo, headers=bearer(esc.recepcion))
    assert r.status_code == 422
    assert (await turno(session_factory, turno_id)).estado == "atendido"


async def test_deshacer_y_marcar_ausente_deja_la_sena_no_reembolsada_y_las_dos_acciones_auditadas(session_factory, client: AsyncClient, esc, reloj) -> None:  # type: ignore[no-untyped-def]
    inicio = local(DIA, "09:00")
    turno_id = await atendido(session_factory, esc, inicio)
    reloj(inicio + timedelta(minutes=30))
    assert (await deshacer(client, esc.recepcion, turno_id)).status_code == 200
    ausente = await client.post(f"/api/panel/turnos/{turno_id}/ausente", headers=bearer(esc.recepcion))
    assert ausente.status_code == 200 and ausente.json()["estado_sena"] == "no_reembolsado"
    assert (await turno(session_factory, turno_id)).estado == "ausente"
    assert await pago_estado(session_factory, turno_id) == "no_reembolsado"  # R9
    origenes = [a.datos_despues["origen"] for a in await auditorias(session_factory, "UPDATE")
                if a.entidad == "turno" and a.entidad_id == str(turno_id)]
    assert origenes == ["deshacer_atendido_panel", "marcado_ausente_panel"]


# --- 5.5 Plazo -------------------------------------------------------------------------------------------------

async def test_a_las_26_horas_se_acepta_y_a_los_10_dias_da_409_plazo_vencido_con_el_limite(session_factory, client: AsyncClient, esc, reloj) -> None:  # type: ignore[no-untyped-def]
    reciente = await atendido(session_factory, esc, en(date(2026, 11, 9), "07:00"), con_sena=False)
    assert (await deshacer(client, esc.admin, reciente)).status_code == 200
    viejo_inicio = en(date(2026, 10, 31), "09:00")
    viejo = await atendido(session_factory, esc, viejo_inicio, con_sena=False)
    r = await deshacer(client, esc.recepcion, viejo)
    assert r.status_code == 409 and r.json()["motivo"] == "plazo_vencido"
    assert r.json()["limite_correccion"] == "2026-11-07T09:00:00-03:00"
    assert (await turno(session_factory, viejo)).estado == "atendido"


async def test_el_limite_exacto_se_acepta_un_segundo_despues_no_y_un_id_inexistente_da_404(session_factory, client: AsyncClient, esc, reloj) -> None:  # type: ignore[no-untyped-def]
    inicio = local(date(2026, 11, 10), "09:00")
    exacto = await atendido(session_factory, esc, inicio, con_sena=False)
    tarde = await atendido(session_factory, esc, inicio, con_sena=False, prof="bruno")
    reloj(datetime(2026, 11, 17, 9, 0, 0, tzinfo=inicio.tzinfo))
    assert (await deshacer(client, esc.recepcion, exacto)).status_code == 200
    reloj(datetime(2026, 11, 17, 9, 0, 1, tzinfo=inicio.tzinfo))
    assert (await deshacer(client, esc.recepcion, tarde)).status_code == 409
    assert (await deshacer(client, esc.recepcion, 999999)).status_code == 404


# --- 5.6 Auditoría y sin avisos ---------------------------------------------------------------------------------

async def test_la_correccion_queda_auditada_sin_datos_personales_y_no_publica_eventos(session_factory, client: AsyncClient, esc, notificador: NotificadorEspia) -> None:  # type: ignore[no-untyped-def]
    turno_id = await atendido(session_factory, esc, local(DIA, "10:00"))
    assert (await deshacer(client, esc.recepcion, turno_id, "turno_equivocado")).status_code == 200
    [a] = [x for x in await auditorias(session_factory, "UPDATE") if x.entidad == "turno"]
    assert (a.usuario_id, a.entidad_id, a.datos_antes, a.datos_despues) == (
        esc.recepcion_id, str(turno_id), {"estado": "atendido"},
        {"estado": "reservado", "origen": "deshacer_atendido_panel", "motivo": "turno_equivocado"})
    assert "Lucía" not in str(a.datos_despues) and "5491100000011" not in str(a.datos_despues)
    assert notificador.eventos == []


async def test_las_correcciones_rechazadas_no_dejan_auditoria(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    ausente = await insertar_turno(session_factory, esc.mundo, local(DIA, "10:00"), estado="ausente", origen="manual")
    viejo = await atendido(session_factory, esc, en(date(2026, 10, 20), "09:00"), con_sena=False)
    assert (await deshacer(client, esc.recepcion, ausente)).status_code == 409
    assert (await deshacer(client, esc.recepcion, viejo)).status_code == 409
    assert (await deshacer(client, esc.ana, viejo)).status_code == 403
    async with session_factory() as s:
        assert (await s.execute(select(RegistroAuditoria))).first() is None


async def test_dos_correcciones_simultaneas_dejan_un_200_un_409_y_un_solo_registro(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    turno_id = await atendido(session_factory, esc, local(DIA, "10:00"))
    a, b = await asyncio.gather(deshacer(client, esc.recepcion, turno_id), deshacer(client, esc.admin, turno_id))
    assert sorted([a.status_code, b.status_code]) == [200, 409]
    assert len([x for x in await auditorias(session_factory, "UPDATE") if x.entidad == "turno"]) == 1
    assert (await turno(session_factory, turno_id)).estado == "reservado"


# --- 5.8 La agenda informa la acción ----------------------------------------------------------------------------

async def _agenda(client: AsyncClient, token: str, dia: date) -> dict[int, list[str]]:
    r = await client.get("/api/panel/agenda", params={"vista": "dia", "fecha": dia.isoformat()}, headers=bearer(token))
    assert r.status_code == 200, r.text
    return {t["id"]: t["acciones"] for t in r.json()["turnos"]}


async def test_la_agenda_trae_deshacer_atendido_solo_dentro_del_plazo_y_solo_para_recepcion_y_admin(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    hace_2 = await atendido(session_factory, esc, en(date(2026, 11, 8), "10:00"), con_sena=False)
    hace_8 = await atendido(session_factory, esc, en(date(2026, 11, 2), "10:00"), con_sena=False)
    ausente = await insertar_turno(session_factory, esc.mundo, en(date(2026, 11, 9), "10:00"), estado="ausente",
                                   origen="manual")
    cancel_dia = await atendido(session_factory, esc, en(date(2026, 11, 8), "11:00"), con_sena=False, prof="bruno")
    d8, d2, d9 = date(2026, 11, 2), date(2026, 11, 8), date(2026, 11, 9)
    for token in (esc.recepcion, esc.admin):
        assert (await _agenda(client, token, d2))[hace_2] == ["deshacer_atendido"]
        assert (await _agenda(client, token, d8))[hace_8] == []
        assert (await _agenda(client, token, d9))[ausente] == []
        assert (await _agenda(client, token, d2))[cancel_dia] == ["deshacer_atendido"]
    assert (await _agenda(client, esc.ana, d2))[hace_2] == []  # la odontóloga dueña del turno: ninguna acción
    assert (await _agenda(client, esc.ana, d8))[hace_8] == []
