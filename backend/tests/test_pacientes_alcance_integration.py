"""C-11 (3.2, 3.3): ``alcance_paciente`` (O2, O3, O4, O16) contra PostgreSQL real. Datos sintéticos (R19)."""

from datetime import timedelta

import pytest
from app.auth.rbac import PermissionContext
from app.pacientes.alcance import VENTANA_ACCESO_CLINICO, alcance_paciente
from app.pacientes.errores import PacienteAjenoError, PacienteInexistenteError
from app.panel.service import SinProfesionalAsociadoError
from tests.clinica_helpers import AHORA, Escenario, crear_paciente, hace, sembrar_escenario, turno_de
from tests.conftest import crear_usuario_panel


def _ctx(usuario_id: int, *roles: str) -> PermissionContext:
    return PermissionContext(usuario_id=usuario_id, email="x@turnos.test", roles=list(roles))


@pytest.fixture
async def esc(session_factory) -> Escenario:  # type: ignore[no-untyped-def]
    return await sembrar_escenario(session_factory)


async def _alcance(session_factory, contexto: PermissionContext, paciente_id: int):  # type: ignore[no-untyped-def]
    async with session_factory() as s:
        return await alcance_paciente(s, contexto, paciente_id, AHORA)


def test_la_ventana_es_de_365_dias() -> None:
    assert VENTANA_ACCESO_CLINICO == timedelta(days=365)


@pytest.mark.parametrize("rol", ["recepcion", "admin"])
async def test_recepcion_y_admin_tienen_todo(session_factory, esc: Escenario, rol: str) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    a = await _alcance(session_factory, _ctx(esc.recepcion_id, rol), paciente)
    assert (a.nivel, a.escribe_clinica, a.escribe_administrativo, a.ve_contacto, a.ve_pagos) == (
        "total", True, True, True, True)


async def test_odontologa_con_atendido_hace_un_ano_escribe_solo_lo_clinico(session_factory, esc: Escenario) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    await turno_de(session_factory, esc, paciente, hace(dias=330))  # unos once meses
    a = await _alcance(session_factory, _ctx(esc.ana_id, "odontologo"), paciente)
    assert (a.nivel, a.escribe_clinica, a.escribe_administrativo, a.ve_contacto, a.ve_pagos) == (
        "clinico_completo", True, False, False, False)


@pytest.mark.parametrize("estado", ["reservado", "confirmado", "ausente", "cancelado", "en_espera"])
async def test_un_unico_turno_sin_atender_no_da_acceso(session_factory, esc: Escenario, estado: str) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    await turno_de(session_factory, esc, paciente, AHORA + timedelta(days=3), estado,
                   vence=AHORA + timedelta(days=3))
    with pytest.raises(PacienteAjenoError):
        await _alcance(session_factory, _ctx(esc.ana_id, "odontologo"), paciente)


async def test_atendido_solo_con_otra_profesional_es_ajeno(session_factory, esc: Escenario) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    await turno_de(session_factory, esc, paciente, hace(dias=10), "atendido", prof="bruno")
    with pytest.raises(PacienteAjenoError):
        await _alcance(session_factory, _ctx(esc.ana_id, "odontologo"), paciente)
    ok = await _alcance(session_factory, _ctx(esc.bruno_id, "odontologo"), paciente)
    assert ok.nivel == "clinico_completo"


async def test_usuario_con_recepcion_y_odontologa_tiene_permisos_completos(session_factory, esc: Escenario) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    usuario_id, _ = await crear_usuario_panel(session_factory, "multi@turnos.test", ["odontologo", "recepcion"],
                                              profesional_id=esc.mundo["ana"])
    a = await _alcance(session_factory, _ctx(usuario_id, "odontologo", "recepcion"), paciente)
    assert a.nivel == "total" and a.escribe_administrativo and a.ve_pagos


async def test_odontologa_sin_profesional_asociado(session_factory, esc: Escenario) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    usuario_id, _ = await crear_usuario_panel(session_factory, "sinprof@turnos.test", ["odontologo"])
    with pytest.raises(SinProfesionalAsociadoError):
        await _alcance(session_factory, _ctx(usuario_id, "odontologo"), paciente)


async def test_paciente_inexistente_se_valida_antes_que_el_alcance(session_factory, esc: Escenario) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(PacienteInexistenteError):
        await _alcance(session_factory, _ctx(esc.ana_id, "odontologo"), 987654)
    with pytest.raises(PacienteInexistenteError):
        await _alcance(session_factory, _ctx(esc.recepcion_id, "recepcion"), 987654)


# --- Ventana de O16 --------------------------------------------------------------------------------------------

async def test_atendido_hace_11_meses_es_completo(session_factory, esc: Escenario) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    await turno_de(session_factory, esc, paciente, hace(dias=335))
    a = await _alcance(session_factory, _ctx(esc.ana_id, "odontologo"), paciente)
    assert (a.nivel, a.escribe_clinica) == ("clinico_completo", True)


async def test_atendido_hace_13_meses_sin_pendiente_es_solo_lectura(session_factory, esc: Escenario) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    await turno_de(session_factory, esc, paciente, hace(dias=395))
    a = await _alcance(session_factory, _ctx(esc.ana_id, "odontologo"), paciente)
    assert (a.nivel, a.escribe_clinica) == ("clinico_lectura", False)
    assert (a.ve_contacto, a.ve_pagos, a.escribe_administrativo) == (False, False, False)


async def test_13_meses_mas_confirmado_futuro_con_ella_es_completo(session_factory, esc: Escenario) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    await turno_de(session_factory, esc, paciente, hace(dias=395))
    await turno_de(session_factory, esc, paciente, AHORA + timedelta(days=7), "confirmado")
    a = await _alcance(session_factory, _ctx(esc.ana_id, "odontologo"), paciente)
    assert a.nivel == "clinico_completo"


@pytest.mark.parametrize("estado,prof", [("en_espera", "ana"), ("confirmado", "bruno"), ("cancelado", "ana"),
                                          ("ausente", "ana")])
async def test_pendiente_que_no_cuenta_deja_solo_lectura(session_factory, esc: Escenario, estado: str, prof: str) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    await turno_de(session_factory, esc, paciente, hace(dias=395))
    await turno_de(session_factory, esc, paciente, AHORA + timedelta(days=7), estado, prof=prof,
                   vence=AHORA + timedelta(days=7))
    a = await _alcance(session_factory, _ctx(esc.ana_id, "odontologo"), paciente)
    assert a.nivel == "clinico_lectura"


async def test_solo_un_confirmado_futuro_sin_atencion_previa_es_ajeno(session_factory, esc: Escenario) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    await turno_de(session_factory, esc, paciente, AHORA + timedelta(days=1), "confirmado")
    with pytest.raises(PacienteAjenoError):
        await _alcance(session_factory, _ctx(esc.ana_id, "odontologo"), paciente)


@pytest.mark.parametrize("segundos_extra,nivel", [(0, "clinico_completo"), (1, "clinico_lectura")])
async def test_borde_de_365_dias_exactos_y_un_segundo_mas(session_factory, esc: Escenario,  # type: ignore[no-untyped-def]
                                                          segundos_extra: int, nivel: str) -> None:
    paciente = await crear_paciente(session_factory)
    await turno_de(session_factory, esc, paciente, AHORA - VENTANA_ACCESO_CLINICO - timedelta(seconds=segundos_extra))
    assert (await _alcance(session_factory, _ctx(esc.ana_id, "odontologo"), paciente)).nivel == nivel


async def test_turno_reservado_de_hoy_en_curso_extiende_el_acceso(session_factory, esc: Escenario) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    await turno_de(session_factory, esc, paciente, hace(dias=395))
    await turno_de(session_factory, esc, paciente, AHORA - timedelta(minutes=10), "reservado", minutos=30)
    a = await _alcance(session_factory, _ctx(esc.ana_id, "odontologo"), paciente)
    assert a.nivel == "clinico_completo"


async def test_turno_reservado_ya_terminado_no_extiende_el_acceso(session_factory, esc: Escenario) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    await turno_de(session_factory, esc, paciente, hace(dias=395))
    await turno_de(session_factory, esc, paciente, AHORA - timedelta(hours=2), "reservado", minutos=30)
    a = await _alcance(session_factory, _ctx(esc.ana_id, "odontologo"), paciente)
    assert a.nivel == "clinico_lectura"


# --- 3.3 Primera visita (D2) -----------------------------------------------------------------------------------

async def test_primera_visita_403_hasta_que_se_marca_atendido_y_vuelve_a_403_si_se_desvincula(  # type: ignore[no-untyped-def]
        session_factory, client, reloj, esc: Escenario) -> None:
    from tests.conftest import bearer

    paciente = await crear_paciente(session_factory)
    otro = await crear_paciente(session_factory)
    inicio = AHORA + timedelta(hours=1)
    turno_id = await turno_de(session_factory, esc, paciente, inicio, "reservado")
    reloj(AHORA)
    with pytest.raises(PacienteAjenoError):
        await _alcance(session_factory, _ctx(esc.ana_id, "odontologo"), paciente)

    resp = await client.post(f"/api/panel/turnos/{turno_id}/atendido", headers=bearer(esc.recepcion))
    assert resp.status_code == 200, resp.text
    a = await _alcance(session_factory, _ctx(esc.ana_id, "odontologo"), paciente)
    assert (a.nivel, a.escribe_clinica) == ("clinico_completo", True)

    # re-vincular el turno con otro paciente (corrección de recepción): el acceso al primero se pierde
    resp = await client.put(f"/api/panel/turnos/{turno_id}/paciente", json={"paciente_id": otro},
                            headers=bearer(esc.recepcion))
    assert resp.status_code == 200, resp.text
    with pytest.raises(PacienteAjenoError):
        await _alcance(session_factory, _ctx(esc.ana_id, "odontologo"), paciente)
