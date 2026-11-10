"""C-11 (11.1): red de seguridad de la matriz D1, ruta × actor. Datos sintéticos (R19).

Actores: recepción, admin y la Dra. Ana Ficticia con acceso completo (``completo``: atendida hace 60 días), de solo
lectura (``lectura``: atendida hace 400 días) y ajena (``ajena``: solo un turno ``confirmado``).
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import pytest
from httpx import AsyncClient, Response

from tests.clinica_helpers import AHORA, Escenario, crear_paciente, hace, sembrar_escenario, turno_de
from tests.conftest import bearer
from tests.presupuestos_helpers import crear_presupuesto, sembrar_catalogo, transicionar

ACTORES = ("recepcion", "admin", "completo", "lectura", "ajena")
PROHIBIDAS_PARA_LA_ODONTOLOGA = {"telefono", "email", "pagos", "saldo", "total_pagado"}


@dataclass
class Ctx:
    client: AsyncClient
    esc: Escenario
    cat: dict[str, int]
    paciente: int
    token: str
    factory: Any

    @property
    def h(self) -> dict[str, str]:
        return bearer(self.token)

    def p(self, resto: str = "") -> str:
        return f"/api/panel/pacientes/{self.paciente}{resto}"

    async def presupuesto(self, estado: str = "borrador") -> int:
        """Presupuesto del paciente en el estado pedido, armado por recepción."""
        pid = int((await crear_presupuesto(self.client, self.esc.recepcion, self.paciente,
                                           (self.cat["limpieza"], 1))).json()["id"])
        for accion in {"borrador": [], "presentado": ["presentar"], "aceptado": ["presentar", "aceptar"]}[estado]:
            assert (await transicionar(self.client, self.esc.recepcion, self.paciente, pid, accion)).status_code == 200
        return pid


async def _ficha_v(c: Ctx) -> int:
    return int((await c.client.get(c.p("/ficha"), headers=bearer(c.esc.recepcion))).json()["version"])


# (nombre, ejecutor, {actor: código esperado})
Celda = tuple[str, Callable[[Ctx], Awaitable[Response]], dict[str, int]]


def _a(rec: int, adm: int, comp: int, lect: int, aj: int) -> dict[str, int]:
    return dict(zip(ACTORES, (rec, adm, comp, lect, aj)))


async def _post_paciente(c: Ctx) -> Response:
    dni = str(99100000 + ACTORES.index("completo") + hash(c.token) % 1000)
    return await c.client.post("/api/panel/pacientes", headers=c.h, json={
        "nombre": "Nuevo", "apellido": "Sintético", "dni": dni, "telefono": "+5491100000099"})


async def _put_paciente(c: Ctx) -> Response:
    return await c.client.put(c.p(), headers=c.h, json={
        "nombre": "Lucía", "apellido": "Ejemplo", "dni": "99000001", "telefono": "+5491100000002"})


async def _vincular(c: Ctx) -> Response:
    turno = await turno_de(c.factory, c.esc, None, AHORA + timedelta(days=9), "reservado", origen="manual",
                           con_codigo=False)
    return await c.client.put(f"/api/panel/turnos/{turno}/paciente", headers=c.h, json={"paciente_id": c.paciente})


async def _put_ficha(c: Ctx) -> Response:
    return await c.client.put(c.p("/ficha"), headers=c.h, json={
        "alergias": "", "medicacion": "", "antecedentes_medicos": "", "observaciones": "", "version": await _ficha_v(c)})


async def _post_odontograma(c: Ctx) -> Response:
    return await c.client.post(c.p("/odontograma"), headers=c.h, json={
        "registros": [{"pieza": 16, "cara": "O", "estado": "caries"}]})


async def _post_presupuesto(c: Ctx) -> Response:
    return await c.client.post(c.p("/presupuestos"), headers=c.h, json={
        "lineas": [{"tratamiento_id": c.cat["limpieza"], "cantidad": 1}]})


async def _put_presupuesto(c: Ctx) -> Response:
    pid = await c.presupuesto()
    return await c.client.put(c.p(f"/presupuestos/{pid}"), headers=c.h, json={
        "lineas": [{"tratamiento_id": c.cat["limpieza"], "cantidad": 2}]})


def _transicion(accion: str, previo: str, cuerpo: dict[str, Any] | None = None) -> Callable[[Ctx], Awaitable[Response]]:
    async def _run(c: Ctx) -> Response:
        pid = await c.presupuesto(previo)
        return await c.client.post(c.p(f"/presupuestos/{pid}/{accion}"), headers=c.h, json=cuerpo or {})
    return _run


async def _get_presupuesto(c: Ctx) -> Response:
    return await c.client.get(c.p(f"/presupuestos/{await c.presupuesto()}"), headers=c.h)


async def _get_pagos(c: Ctx) -> Response:
    return await c.client.get(c.p(f"/presupuestos/{await c.presupuesto('aceptado')}/pagos"), headers=c.h)


async def _post_pago(c: Ctx) -> Response:
    pid = await c.presupuesto("aceptado")
    return await c.client.post(c.p(f"/presupuestos/{pid}/pagos"), headers=c.h,
                               json={"medio": "transferencia", "monto": "100.00"})


async def _anular_pago(c: Ctx) -> Response:
    pid = await c.presupuesto("aceptado")
    pago = (await c.client.post(c.p(f"/presupuestos/{pid}/pagos"), headers=bearer(c.esc.recepcion),
                                json={"medio": "transferencia", "monto": "100.00"})).json()["pago"]["id"]
    return await c.client.post(c.p(f"/presupuestos/{pid}/pagos/{pago}/anular"), headers=c.h,
                               json={"motivo": "error de carga"})


def _get(resto: str) -> Callable[[Ctx], Awaitable[Response]]:
    async def _run(c: Ctx) -> Response:
        return await c.client.get(c.p(resto), headers=c.h)
    return _run


async def _buscar_dni(c: Ctx) -> Response:
    return await c.client.get("/api/panel/pacientes", params={"dni": "99000001"}, headers=c.h)


def _atendido(propiedad: str) -> Callable[[Ctx], Awaitable[Response]]:
    async def _run(c: Ctx) -> Response:
        if propiedad == "inexistente":
            return await c.client.post("/api/panel/turnos/987654/atendido", headers=c.h)
        profesional = "ana" if propiedad == "propio" else "bruno"
        turno = await turno_de(c.factory, c.esc, None, AHORA + timedelta(hours=1), "reservado", prof=profesional)
        return await c.client.post(f"/api/panel/turnos/{turno}/atendido", headers=c.h)
    return _run


MATRIZ: list[Celda] = [
    ("POST /pacientes", _post_paciente, _a(201, 201, 403, 403, 403)),
    ("GET /pacientes?dni=", _buscar_dni, _a(200, 200, 403, 403, 403)),
    ("GET /pacientes/{id}", _get(""), _a(200, 200, 200, 200, 403)),
    ("PUT /pacientes/{id}", _put_paciente, _a(200, 200, 403, 403, 403)),
    ("PUT /turnos/{id}/paciente", _vincular, _a(200, 200, 403, 403, 403)),
    ("GET ficha", _get("/ficha"), _a(200, 200, 200, 200, 403)),
    ("PUT ficha", _put_ficha, _a(200, 200, 200, 403, 403)),
    ("GET odontograma", _get("/odontograma"), _a(200, 200, 200, 200, 403)),
    ("GET odontograma/historial", _get("/odontograma/historial"), _a(200, 200, 200, 200, 403)),
    ("POST odontograma", _post_odontograma, _a(201, 201, 201, 403, 403)),
    ("GET presupuestos", _get("/presupuestos"), _a(200, 200, 200, 200, 403)),
    ("GET presupuestos/{pid}", _get_presupuesto, _a(200, 200, 200, 200, 403)),
    ("POST presupuestos", _post_presupuesto, _a(201, 201, 403, 403, 403)),
    ("PUT presupuestos/{pid}", _put_presupuesto, _a(200, 200, 403, 403, 403)),
    ("POST presentar", _transicion("presentar", "borrador"), _a(200, 200, 403, 403, 403)),
    ("POST aceptar", _transicion("aceptar", "presentado"), _a(200, 200, 403, 403, 403)),
    ("POST rechazar", _transicion("rechazar", "presentado"), _a(200, 200, 403, 403, 403)),
    ("POST anular", _transicion("anular", "borrador", {"motivo": "no corresponde"}), _a(200, 200, 403, 403, 403)),
    ("GET pagos", _get_pagos, _a(200, 200, 403, 403, 403)),
    ("POST pagos", _post_pago, _a(201, 201, 403, 403, 403)),
    ("POST pagos/{id}/anular", _anular_pago, _a(200, 200, 403, 403, 403)),
    ("POST turnos/{id}/atendido (propio)", _atendido("propio"), _a(200, 200, 200, 200, 200)),
    ("POST turnos/{id}/atendido (ajeno)", _atendido("ajeno"), _a(200, 200, 403, 403, 403)),
    ("POST turnos/{id}/atendido (inexistente)", _atendido("inexistente"), _a(404, 404, 403, 403, 403)),
]


def _claves(valor: Any) -> set[str]:
    if isinstance(valor, dict):
        return set(valor) | {k for v in valor.values() for k in _claves(v)}
    if isinstance(valor, list):
        return {k for v in valor for k in _claves(v)}
    return set()


@pytest.mark.parametrize("actor", ACTORES)
@pytest.mark.parametrize("nombre,ejecutor,esperado", MATRIZ, ids=[m[0] for m in MATRIZ])
async def test_celda_de_la_matriz(session_factory, client: AsyncClient, reloj, actor: str, nombre: str,  # type: ignore[no-untyped-def]
                                  ejecutor: Callable[[Ctx], Awaitable[Response]], esperado: dict[str, int]) -> None:
    reloj(AHORA)
    esc = await sembrar_escenario(session_factory)
    cat = await sembrar_catalogo(session_factory)
    paciente = await crear_paciente(session_factory, dni="99000001", obra_social_id=cat["swiss"])
    if actor == "lectura":
        await turno_de(session_factory, esc, paciente, hace(dias=400))
    elif actor == "ajena":
        await turno_de(session_factory, esc, paciente, AHORA + timedelta(days=2), "confirmado")
    else:
        await turno_de(session_factory, esc, paciente, hace(dias=60))
    token = {"recepcion": esc.recepcion, "admin": esc.admin}.get(actor, esc.ana)
    resp = await ejecutor(Ctx(client, esc, cat, paciente, token, session_factory))
    assert resp.status_code == esperado[actor], f"{nombre} / {actor}: {resp.status_code} {resp.text}"
    if actor in ("completo", "lectura", "ajena") and resp.status_code < 300:
        assert not PROHIBIDAS_PARA_LA_ODONTOLOGA & _claves(resp.json()), f"{nombre}: filtra datos prohibidos"
