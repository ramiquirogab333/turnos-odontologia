"""C-13 (2.3, D2, D4): helper único ``registrar`` — misma transacción, guarda de datos personales e IP. Datos sintéticos."""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.core import RegistroAuditoria
from app.plataforma.auditoria import (
    AUTO,
    CLAVES_PROHIBIDAS,
    DatosProhibidosEnAuditoriaError,
    contexto_auditoria,
    registrar,
)
from tests.conftest import bearer, crear_usuario_panel

Factory = async_sessionmaker[AsyncSession]


async def _filas(factory: Factory) -> list[RegistroAuditoria]:
    async with factory() as s:
        return list((await s.execute(select(RegistroAuditoria).order_by(RegistroAuditoria.id))).scalars())


async def test_registrar_agrega_la_fila_en_la_transaccion_del_caller(session_factory: Factory) -> None:
    uid, _ = await crear_usuario_panel(session_factory, "admin@turnos.test", ["admin"])
    async with session_factory() as s:
        registrar(s, accion="cierre_caja", entidad="cierre_caja", entidad_id=42, usuario_id=uid,
                  despues={"total": "1500.00"}, ip="192.0.2.7")
        assert await _filas(session_factory) == []  # todavía no hay commit
        await s.commit()
    [fila] = await _filas(session_factory)
    assert (fila.usuario_id, fila.accion, fila.entidad, fila.entidad_id, fila.ip) == (
        uid, "cierre_caja", "cierre_caja", "42", "192.0.2.7")
    assert fila.datos_despues == {"total": "1500.00"} and fila.datos_antes is None


async def test_un_rollback_no_deja_fila_y_entidad_id_none_se_guarda_nulo(session_factory: Factory) -> None:
    async with session_factory() as s:
        registrar(s, accion="lectura_listado_pacientes", entidad="paciente", entidad_id=None, usuario_id=None)
        await s.rollback()
    assert await _filas(session_factory) == []
    async with session_factory() as s:
        registrar(s, accion="lectura_listado_pacientes", entidad="paciente", entidad_id=None, usuario_id=None)
        await s.commit()
    [fila] = await _filas(session_factory)
    assert fila.entidad_id is None


@pytest.mark.parametrize("clave", ["telefono", "dni", "q", "codigo_gestion", "token", "password", "access_token",
                                   "refresh_token", "contacto_nombre", "contacto_telefono", "url_autorizacion",
                                   "state", "code_verifier", "busqueda", "nombre", "email"])
async def test_una_clave_prohibida_en_primer_nivel_o_anidada_falla_sin_dejar_fila(
        session_factory: Factory, clave: str) -> None:
    assert clave in CLAVES_PROHIBIDAS
    async with session_factory() as s:
        with pytest.raises(DatosProhibidosEnAuditoriaError):
            registrar(s, accion="edicion_paciente", entidad="paciente", entidad_id=1, usuario_id=None,
                      despues={clave: "dato sintético"})
        with pytest.raises(DatosProhibidosEnAuditoriaError):
            registrar(s, accion="edicion_paciente", entidad="paciente", entidad_id=1, usuario_id=None,
                      antes={"filas": [{"ok": 1}, {clave: "x"}]})
        await s.commit()
    assert await _filas(session_factory) == []


async def test_los_nombres_de_campos_como_valores_estan_permitidos(session_factory: Factory) -> None:
    async with session_factory() as s:
        registrar(s, accion="edicion_paciente", entidad="paciente", entidad_id=1, usuario_id=None,
                  despues={"campos": ["telefono", "email"], "con_busqueda": True})
        await s.commit()
    assert len(await _filas(session_factory)) == 1


async def test_ip_auto_sin_pedido_en_curso_es_none_y_un_valor_explicito_se_respeta(session_factory: Factory) -> None:
    async with session_factory() as s:
        registrar(s, accion="barrido_pre_reservas", entidad="turno", entidad_id=1, usuario_id=None)  # AUTO
        registrar(s, accion="barrido_pre_reservas", entidad="turno", entidad_id=2, usuario_id=None, ip=None)
        registrar(s, accion="barrido_pre_reservas", entidad="turno", entidad_id=3, usuario_id=None, ip="198.51.100.4")
        await s.commit()
    assert [f.ip for f in await _filas(session_factory)] == [None, None, "198.51.100.4"]


async def test_ip_auto_toma_la_del_contexto_del_pedido(session_factory: Factory) -> None:
    token = contexto_auditoria.set("203.0.113.9")
    try:
        async with session_factory() as s:
            registrar(s, accion="cierre_caja", entidad="cierre_caja", entidad_id=1, usuario_id=None, ip=AUTO)
            registrar(s, accion="cierre_caja", entidad="cierre_caja", entidad_id=2, usuario_id=None, ip=None)
            await s.commit()
    finally:
        contexto_auditoria.reset(token)
    assert [f.ip for f in await _filas(session_factory)] == ["203.0.113.9", None]


async def test_crear_un_profesional_audita_ids_y_campos_sin_nombre_ni_matricula(
        session_factory: Factory, client: AsyncClient, token_recepcion: str) -> None:
    r = await client.post("/api/admin/profesionales", headers=bearer(token_recepcion),
                          json={"nombre": "Dra. Ficticia", "matricula": "MP-99999", "especialidad": "Ortodoncia"})
    assert r.status_code == 201, r.text
    [fila] = [f for f in await _filas(session_factory) if f.entidad == "profesional"]
    assert (fila.accion, fila.entidad_id) == ("CREATE", str(r.json()["id"]))
    despues: dict[str, Any] = fila.datos_despues
    assert "nombre" not in despues and "matricula" not in despues
    assert despues["id"] == r.json()["id"] and despues["especialidad"] == "Ortodoncia"
    assert {"nombre", "matricula", "especialidad"} <= set(despues["campos"])


async def test_actualizar_un_profesional_audita_solo_los_campos_cambiados(
        session_factory: Factory, client: AsyncClient, token_recepcion: str) -> None:
    creado = (await client.post("/api/admin/profesionales", headers=bearer(token_recepcion),
                                json={"nombre": "Dr. Prueba", "matricula": "MP-1", "especialidad": "General"})).json()
    r = await client.put(f"/api/admin/profesionales/{creado['id']}", headers=bearer(token_recepcion),
                         json={"especialidad": "Endodoncia"})
    assert r.status_code == 200
    fila = [f for f in await _filas(session_factory) if f.accion == "UPDATE"][0]
    assert fila.datos_despues["campos"] == ["especialidad"]
    assert fila.datos_antes["especialidad"] == "General" and fila.datos_despues["especialidad"] == "Endodoncia"
    assert "nombre" not in fila.datos_antes and "nombre" not in fila.datos_despues
