"""C-11 (3.4): helper ``auditar`` (O5, RN-GL-01, R19) contra PostgreSQL real."""

import pytest
from sqlalchemy import select

from app.models.core import RegistroAuditoria
from app.pacientes.auditoria import CLAVES_PROHIBIDAS, DatosProhibidosEnAuditoriaError, auditar
from tests.clinica_helpers import Escenario, auditorias, sembrar_escenario


async def test_escribe_en_la_misma_transaccion_con_el_usuario_actor(session_factory) -> None:  # type: ignore[no-untyped-def]
    esc: Escenario = await sembrar_escenario(session_factory)
    async with session_factory() as s:
        auditar(s, esc.ana_id, "lectura_ficha", "ficha", 77, {"version": 3})
        await s.commit()
    [registro] = await auditorias(session_factory, "lectura_ficha")
    assert (registro.usuario_id, registro.entidad, registro.entidad_id) == (esc.ana_id, "ficha", "77")
    assert registro.datos_despues == {"version": 3}


async def test_un_rollback_no_deja_registro(session_factory) -> None:  # type: ignore[no-untyped-def]
    esc = await sembrar_escenario(session_factory)
    async with session_factory() as s:
        auditar(s, esc.recepcion_id, "edicion_ficha", "ficha", 5, {"campos": ["alergias"]})
        await s.rollback()
    assert await auditorias(session_factory, "edicion_ficha") == []


@pytest.mark.parametrize("clave", sorted(CLAVES_PROHIBIDAS))
async def test_una_clave_prohibida_hace_fallar_la_llamada(session_factory, clave: str) -> None:  # type: ignore[no-untyped-def]
    esc = await sembrar_escenario(session_factory)
    async with session_factory() as s:
        with pytest.raises(DatosProhibidosEnAuditoriaError):
            auditar(s, esc.recepcion_id, "edicion_ficha", "ficha", 5, {clave: "dato sintético"})
        with pytest.raises(DatosProhibidosEnAuditoriaError):  # también anidada
            auditar(s, esc.recepcion_id, "edicion_ficha", "ficha", 5, {"cambios": {clave: "x"}})
        await s.rollback()
    assert (await auditorias(session_factory)) == []


def test_la_lista_cubre_los_datos_clinicos_y_personales() -> None:
    # C-13 (D2) amplía la lista con secretos y datos del contacto público: la base de C-11 sigue incluida.
    assert {"alergias", "medicacion", "antecedentes_medicos", "observaciones", "nota", "estado_odontograma", "nombre",
            "apellido", "dni", "numero_afiliado", "telefono", "email"} <= set(CLAVES_PROHIBIDAS)


async def test_los_nombres_de_campos_como_valores_estan_permitidos(session_factory) -> None:  # type: ignore[no-untyped-def]
    esc = await sembrar_escenario(session_factory)
    async with session_factory() as s:
        auditar(s, esc.recepcion_id, "edicion_paciente", "paciente", 9, {"campos": ["telefono", "email"]})
        await s.commit()
    async with session_factory() as s:
        fila = (await s.execute(select(RegistroAuditoria).where(RegistroAuditoria.accion == "edicion_paciente"))
                ).scalar_one()
    assert fila.datos_despues == {"campos": ["telefono", "email"]}
