"""C-13 (3.1, D4, O9): todo registro de un pedido autenticado guarda la IP real; los trabajos del sistema, ninguna.

R19: IPs de documentación (RFC 5737). Datos sintéticos.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.models.core import RegistroAuditoria
from app.pagos.barrido import expirar_pre_reservas
from app.plataforma.auditoria import contexto_auditoria
from tests.caja_helpers import DIA, auditoria_de, en, sena
from tests.clinica_helpers import Escenario, sembrar_escenario
from tests.conftest import bearer
from tests.panel_helpers import insertar_pago, insertar_turno, local

BASE = "/api/panel"
AHORA = datetime(2026, 11, 19, 15, 0, tzinfo=timezone.utc)  # 12:00 del 19 en la clínica; DIA (17) ya pasó


def _cliente(socket: tuple[str, int] | None) -> AsyncClient:
    from app.main import app

    return AsyncClient(transport=ASGITransport(app=app, client=socket), base_url="https://test")


@pytest.fixture
async def esc(session_factory, reloj) -> Escenario:  # type: ignore[no-untyped-def]
    reloj(AHORA)
    return await sembrar_escenario(session_factory)


async def _ip_de(factory, accion: str, entidad_id: int | None = None) -> list[str | None]:  # type: ignore[no-untyped-def]
    async with factory() as s:
        consulta = select(RegistroAuditoria.ip).where(RegistroAuditoria.accion == accion)
        if entidad_id is not None:
            consulta = consulta.where(RegistroAuditoria.entidad_id == str(entidad_id))
        return list((await s.execute(consulta.order_by(RegistroAuditoria.id))).scalars())


async def test_la_devolucion_de_sena_guarda_la_ip_del_cliente(session_factory, esc) -> None:  # type: ignore[no-untyped-def]
    _, pago_id = await sena(session_factory, esc, acreditado_en=en(DIA, "11:00"), estado="a_reembolsar",
                            turno_estado="cancelado", medio="transferencia", desde=en(DIA, "12:00"))
    async with _cliente(("203.0.113.20", 5000)) as c:
        r = await c.post(f"{BASE}/caja/devoluciones/senas/{pago_id}", json={"referencia": "DEV-SINT-0001"},
                         headers=bearer(esc.recepcion))
    assert r.status_code == 200, r.text
    registros = await auditoria_de(session_factory, "devolucion_sena_registrada")
    assert [x.ip for x in registros] == ["203.0.113.20"]


async def test_un_x_forwarded_for_sin_proxy_de_confianza_se_ignora_al_marcar_ausente(session_factory, esc) -> None:  # type: ignore[no-untyped-def]
    turno_id = await insertar_turno(session_factory, esc.mundo, local(DIA, "08:00"))
    async with _cliente(("192.0.2.50", 5000)) as c:
        r = await c.post(f"{BASE}/turnos/{turno_id}/ausente",
                         headers={**bearer(esc.recepcion), "X-Forwarded-For": "198.51.100.99"})
    assert r.status_code == 200, r.text
    assert await _ip_de(session_factory, "UPDATE", turno_id) == ["192.0.2.50"]


async def test_sin_cliente_conocido_el_registro_queda_sin_ip_nunca_un_texto_inventado(session_factory, esc) -> None:  # type: ignore[no-untyped-def]
    turno_id = await insertar_turno(session_factory, esc.mundo, local(DIA, "08:00"))
    async with _cliente(None) as c:
        r = await c.post(f"{BASE}/turnos/{turno_id}/ausente", headers=bearer(esc.recepcion))
    assert r.status_code == 200, r.text
    assert await _ip_de(session_factory, "UPDATE", turno_id) == [None]


async def test_el_barrido_del_worker_no_guarda_ip_aunque_el_contexto_tenga_una(session_factory) -> None:  # type: ignore[no-untyped-def]
    from tests.panel_helpers import sembrar_mundo

    mundo = await sembrar_mundo(session_factory)
    vence = datetime(2031, 3, 3, 13, 30, tzinfo=timezone.utc)
    turno_id = await insertar_turno(session_factory, mundo, vence, estado="en_espera", vence=vence)
    await insertar_pago(session_factory, turno_id, "pendiente")
    token = contexto_auditoria.set("203.0.113.99")  # un contexto "colado" no debe contagiar al trabajo del sistema
    try:
        async with session_factory() as s:
            assert await expirar_pre_reservas(s, vence + timedelta(minutes=1)) == 1
    finally:
        contexto_auditoria.reset(token)
    assert await _ip_de(session_factory, "UPDATE", turno_id) == [None]


async def test_dos_pedidos_concurrentes_con_ips_distintas_graban_cada_uno_la_suya(session_factory, esc) -> None:  # type: ignore[no-untyped-def]
    uno = await insertar_turno(session_factory, esc.mundo, local(DIA, "08:00"))
    otro = await insertar_turno(session_factory, esc.mundo, local(DIA, "08:30"), prof="bruno", sillon="s2")

    async def marcar(socket: tuple[str, int], turno_id: int) -> int:
        async with _cliente(socket) as c:
            return (await c.post(f"{BASE}/turnos/{turno_id}/ausente", headers=bearer(esc.recepcion))).status_code

    codigos = await asyncio.gather(marcar(("192.0.2.1", 1), uno), marcar(("192.0.2.2", 2), otro))
    assert codigos == [200, 200]
    assert await _ip_de(session_factory, "UPDATE", uno) == ["192.0.2.1"]
    assert await _ip_de(session_factory, "UPDATE", otro) == ["192.0.2.2"]
