"""C-12 (12.1): red de seguridad por rol, ruta × actor, sobre los 14 endpoints nuevos (D1). Datos sintéticos (R19).

Actores: recepción, admin, la Dra. Ana Ficticia (odontóloga) y sin token. Todo C-12 es de recepción y admin; la
odontóloga recibe 403 aunque el turno sea suyo, y anular un cierre es solo de admin (la recepción recibe 403).
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from itertools import count
from typing import Any

import pytest
from httpx import AsyncClient, Response

from tests.caja_helpers import aprobacion, en, sena
from tests.clinica_helpers import Escenario, sembrar_escenario
from tests.conftest import bearer

AHORA = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)  # 09:00 del 18 en la clínica
ACTORES = ("recepcion", "admin", "odontologa", "sin_token")
_dias = count(1)
_referencias = count(1)
_horarios = count(0)


@dataclass
class Ctx:
    client: AsyncClient
    esc: Escenario
    factory: Any
    token: str | None

    @property
    def h(self) -> dict[str, str]:
        return {} if self.token is None else bearer(self.token)

    async def cierre_nuevo(self) -> int:
        """Un cierre vigente de un día terminado distinto en cada llamada, cerrado por admin."""
        dia = date(2026, 9, 1) + timedelta(days=next(_dias))
        r = await self.client.post("/api/panel/caja/cierres", json={"dia": str(dia)}, headers=bearer(self.esc.admin))
        assert r.status_code == 201, r.text
        return int(r.json()["id"])


Celda = tuple[str, Callable[[Ctx], Awaitable[Response]], dict[str, int]]


def _a(rec: int, adm: int, odo: int, anon: int) -> dict[str, int]:
    return dict(zip(ACTORES, (rec, adm, odo, anon)))


SOLO_RECEPCION_Y_ADMIN = _a(200, 200, 403, 401)
ESCRIBE_RECEPCION_Y_ADMIN = _a(200, 200, 403, 401)


async def _get_caja(c: Ctx) -> Response:
    return await c.client.get("/api/panel/caja", params={"dia": "2026-11-17"}, headers=c.h)


async def _post_cierre(c: Ctx) -> Response:
    dia = date(2026, 8, 1) + timedelta(days=next(_dias))
    return await c.client.post("/api/panel/caja/cierres", json={"dia": str(dia)}, headers=c.h)


async def _get_cierres(c: Ctx) -> Response:
    return await c.client.get("/api/panel/caja/cierres", params={"desde": "2026-09-01", "hasta": "2026-11-17"}, headers=c.h)


async def _get_cierre(c: Ctx) -> Response:
    return await c.client.get(f"/api/panel/caja/cierres/{await c.cierre_nuevo()}", headers=c.h)


async def _anular_cierre(c: Ctx) -> Response:
    return await c.client.post(f"/api/panel/caja/cierres/{await c.cierre_nuevo()}/anular",
                               json={"motivo": "cobro cargado en el presupuesto equivocado"}, headers=c.h)


async def _liquidacion(c: Ctx) -> Response:
    return await c.client.get("/api/panel/caja/liquidacion", params={"desde": "2026-11-01", "hasta": "2026-11-17"}, headers=c.h)


async def _pendientes(c: Ctx) -> Response:
    return await c.client.get("/api/panel/caja/pendientes", headers=c.h)


async def _rechazar_revision(c: Ctx) -> Response:
    _, pago = await sena(c.factory, c.esc, acreditado_en=None, estado="en_revision", turno_estado="en_espera")
    return await c.client.post(f"/api/panel/caja/revisiones/{pago}/rechazar", headers=c.h)


async def _devolver_sena(c: Ctx) -> Response:
    _, pago = await sena(c.factory, c.esc, acreditado_en=en(date(2026, 11, 17), "11:00"), estado="a_reembolsar",
                         turno_estado="cancelado")
    return await c.client.post(f"/api/panel/caja/devoluciones/senas/{pago}", headers=c.h,
                               json={"referencia": f"DEV-SINT-{next(_referencias):04d}"})


async def _devolver_excedente(c: Ctx) -> Response:
    n = next(_referencias)
    _, pago = await sena(c.factory, c.esc, acreditado_en=en(date(2026, 11, 17), "11:00"), mp_payment_id=f"MP-RBAC-A{n}")
    aprob = await aprobacion(c.factory, pago, f"MP-RBAC-B{n}")
    return await c.client.post(f"/api/panel/caja/devoluciones/excedentes/{aprob}", headers=c.h,
                               json={"referencia": f"DEV-SINT-{n:04d}"})


async def _ocupacion(c: Ctx) -> Response:
    return await c.client.get("/api/panel/ocupacion", params={"desde": "2026-11-16", "hasta": "2026-11-18"}, headers=c.h)


async def _ausentismo(c: Ctx) -> Response:
    return await c.client.get("/api/panel/ausentismo", params={"desde": "2026-11-01", "hasta": "2026-11-18"}, headers=c.h)


async def _listado(c: Ctx) -> Response:
    return await c.client.get("/api/panel/pacientes/listado", headers=c.h)


async def _deshacer_atendido(c: Ctx) -> Response:
    inicio = en(date(2026, 11, 16), "11:00") + timedelta(minutes=30 * next(_horarios))  # un horario libre por llamada
    turno, _ = await sena(c.factory, c.esc, acreditado_en=inicio - timedelta(days=3), turno_estado="atendido", inicio=inicio)
    return await c.client.post(f"/api/panel/turnos/{turno}/deshacer-atendido", json={"motivo": "turno_equivocado"},
                               headers=c.h)


# (nombre, ejecutor, {actor: código esperado}): son los 14 endpoints nuevos de C-12.
MATRIZ: list[Celda] = [
    ("GET /api/panel/caja", _get_caja, SOLO_RECEPCION_Y_ADMIN),
    ("POST /api/panel/caja/cierres", _post_cierre, _a(201, 201, 403, 401)),
    ("GET /api/panel/caja/cierres", _get_cierres, SOLO_RECEPCION_Y_ADMIN),
    ("GET /api/panel/caja/cierres/{id}", _get_cierre, SOLO_RECEPCION_Y_ADMIN),
    ("POST /api/panel/caja/cierres/{id}/anular", _anular_cierre, _a(403, 200, 403, 401)),
    ("GET /api/panel/caja/liquidacion", _liquidacion, SOLO_RECEPCION_Y_ADMIN),
    ("GET /api/panel/caja/pendientes", _pendientes, SOLO_RECEPCION_Y_ADMIN),
    ("POST /api/panel/caja/revisiones/{pago}/rechazar", _rechazar_revision, ESCRIBE_RECEPCION_Y_ADMIN),
    ("POST /api/panel/caja/devoluciones/senas/{pago}", _devolver_sena, ESCRIBE_RECEPCION_Y_ADMIN),
    ("POST /api/panel/caja/devoluciones/excedentes/{aprobacion}", _devolver_excedente, ESCRIBE_RECEPCION_Y_ADMIN),
    ("GET /api/panel/ocupacion", _ocupacion, SOLO_RECEPCION_Y_ADMIN),
    ("GET /api/panel/ausentismo", _ausentismo, SOLO_RECEPCION_Y_ADMIN),
    ("GET /api/panel/pacientes/listado", _listado, SOLO_RECEPCION_Y_ADMIN),
    ("POST /api/panel/turnos/{id}/deshacer-atendido", _deshacer_atendido, ESCRIBE_RECEPCION_Y_ADMIN),
]

# El POST de cierre y los de escritura devuelven 201 o 200: el código esperado ya lo dice la matriz.
CASOS = [pytest.param(nombre, ejecutor, actor, esperado[actor], id=f"{nombre} :: {actor}")
         for nombre, ejecutor, esperado in MATRIZ for actor in ACTORES]


@pytest.fixture
async def esc(session_factory, reloj) -> Escenario:  # type: ignore[no-untyped-def]
    reloj(AHORA)
    return await sembrar_escenario(session_factory)


def test_la_matriz_cubre_los_14_endpoints_nuevos_con_los_cuatro_actores() -> None:
    assert len(MATRIZ) == 14
    assert len({nombre for nombre, _, _ in MATRIZ}) == 14
    assert all(set(esperado) == set(ACTORES) for _, _, esperado in MATRIZ)
    assert len(CASOS) == 14 * 4


@pytest.mark.parametrize(("nombre", "ejecutor", "actor", "esperado"), CASOS)
async def test_codigo_por_ruta_y_actor(session_factory, client: AsyncClient, esc: Escenario, nombre: str,  # type: ignore[no-untyped-def]
                                       ejecutor: Callable[[Ctx], Awaitable[Response]], actor: str, esperado: int) -> None:
    token = {"recepcion": esc.recepcion, "admin": esc.admin, "odontologa": esc.ana, "sin_token": None}[actor]
    r = await ejecutor(Ctx(client, esc, session_factory, token))
    assert r.status_code == esperado, f"{nombre} como {actor}: {r.status_code} {r.text}"


async def test_los_rechazos_por_rol_no_filtran_datos_ni_cambian_estados(session_factory, client: AsyncClient, esc: Escenario) -> None:  # type: ignore[no-untyped-def]
    """Un 403 o 401 no cuenta nada de lo que protege: el cuerpo trae solo el motivo."""
    for nombre, ejecutor, esperado in MATRIZ:
        for actor in ("odontologa", "sin_token"):
            token = esc.ana if actor == "odontologa" else None
            r = await ejecutor(Ctx(client, esc, session_factory, token))
            assert r.status_code == esperado[actor], f"{nombre} como {actor}"
            cuerpo = r.json()
            assert set(cuerpo) == {"detail"} or set(cuerpo) == {"detail", "motivo"}, f"{nombre}: {cuerpo}"
