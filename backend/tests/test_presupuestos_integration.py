"""C-11 (grupo 7): presupuestos con cobertura, estados, congelamiento y permisos por rol. Datos sintéticos (R19)."""

from datetime import timedelta
from decimal import Decimal

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import event, select, update

from app.models.core import Nomenclador
from app.shared.db import get_engine
from app.turnos.models import Tratamiento
from tests.clinica_helpers import AHORA, Escenario, auditorias, contar, crear_obra_social, crear_paciente, hace, \
    sembrar_escenario, turno_de
from tests.conftest import bearer
from tests.presupuestos_helpers import (
    aceptado, crear_presupuesto, insertar_pago, lineas, sembrar_catalogo, transicionar, tratamiento_sintetico,
)


@pytest.fixture
async def esc(session_factory, reloj) -> Escenario:  # type: ignore[no-untyped-def]
    reloj(AHORA)
    return await sembrar_escenario(session_factory)


@pytest.fixture
async def cat(session_factory, esc) -> dict[str, int]:  # type: ignore[no-untyped-def]
    return await sembrar_catalogo(session_factory)


def _url(paciente: int, resto: str = "") -> str:
    return f"/api/panel/pacientes/{paciente}/presupuestos{resto}"


# --- 7.1 / 7.2 Cálculo ---------------------------------------------------------------------------------------

async def test_limpieza_con_swiss_deja_2500_a_cargo(session_factory, client: AsyncClient, esc, cat) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory, obra_social_id=cat["swiss"])
    resp = await crear_presupuesto(client, esc.recepcion, paciente, (cat["limpieza"], 1))
    assert resp.status_code == 201, resp.text
    cuerpo = resp.json()
    [linea] = cuerpo["lineas"]
    assert (linea["importe_bruto"], linea["importe_cobertura"], linea["importe_diferencial"],
            linea["importe_paciente"], linea["sin_cobertura"]) == ("25000.00", "22500.00", "0.00", "2500.00", False)
    assert (cuerpo["estado"], cuerpo["obra_social"]["id"], cuerpo["total_paciente"]) == (
        "borrador", cat["swiss"], "2500.00")
    assert cuerpo["pagos"] == [] and cuerpo["total_pagado"] == "0.00" and cuerpo["saldo"] == "2500.00"


async def test_dos_lineas_suman_totales_de_lineas(session_factory, client: AsyncClient, esc, cat) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory, obra_social_id=cat["swiss"])
    cuerpo = (await crear_presupuesto(client, esc.recepcion, paciente, (cat["limpieza"], 1), (cat["consulta"], 1))).json()
    assert (cuerpo["subtotal"], cuerpo["cobertura_total"], cuerpo["diferencial_total"], cuerpo["total_paciente"]) == (
        "40000.00", "36000.00", "0.00", "4000.00")


async def test_paciente_particular_queda_sin_cobertura(session_factory, client: AsyncClient, esc, cat) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    cuerpo = (await crear_presupuesto(client, esc.recepcion, paciente, (cat["limpieza"], 1))).json()
    [linea] = cuerpo["lineas"]
    assert (cuerpo["obra_social"], cuerpo["total_paciente"], linea["importe_cobertura"], linea["sin_cobertura"]) == (
        None, "25000.00", "0.00", True)


async def test_redondeo_half_up_y_diferencial_por_unidad(session_factory, client: AsyncClient, esc, cat) -> None:  # type: ignore[no-untyped-def]
    chico = await tratamiento_sintetico(session_factory, "Tratamiento sintético A", "10.10",
                                        obra_social_id=cat["omint"], cobertura="85.00")
    grande = await tratamiento_sintetico(session_factory, "Tratamiento sintético B", "25000.00",
                                         obra_social_id=cat["swiss"], cobertura="90.00", diferencial="1500.00")
    omint = await crear_paciente(session_factory, obra_social_id=cat["omint"])
    swiss = await crear_paciente(session_factory, obra_social_id=cat["swiss"])
    [a] = (await crear_presupuesto(client, esc.recepcion, omint, (chico, 1))).json()["lineas"]
    assert (a["importe_cobertura"], a["importe_paciente"]) == ("8.59", "1.51")
    [b] = (await crear_presupuesto(client, esc.recepcion, swiss, (grande, 2))).json()["lineas"]
    assert (b["importe_bruto"], b["importe_cobertura"], b["importe_diferencial"], b["importe_paciente"]) == (
        "50000.00", "45000.00", "3000.00", "8000.00")


@pytest.mark.parametrize("campo", ["importe_paciente", "precio_unitario"])
async def test_importes_enviados_por_el_cliente_son_422(session_factory, client: AsyncClient, esc, cat, campo: str) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory, obra_social_id=cat["swiss"])
    resp = await client.post(_url(paciente), headers=bearer(esc.recepcion), json={
        "lineas": [{"tratamiento_id": cat["limpieza"], "cantidad": 1, campo: "1.00"}]})
    assert resp.status_code == 422
    assert await contar(session_factory, "presupuesto") == 0


async def test_la_creacion_ejecuta_un_numero_constante_de_consultas(session_factory, client: AsyncClient, esc, cat) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory, obra_social_id=cat["swiss"])
    contador = {"n": 0}

    def _contar(*_: object) -> None:
        contador["n"] += 1

    motor = get_engine().sync_engine
    event.listen(motor, "before_cursor_execute", _contar)
    try:
        await crear_presupuesto(client, esc.recepcion, paciente, (cat["limpieza"], 1))
        una = contador["n"]
        contador["n"] = 0
        await crear_presupuesto(client, esc.recepcion, paciente, *[(cat["limpieza"], 1)] * 10)
        diez = contador["n"]
    finally:
        event.remove(motor, "before_cursor_execute", _contar)
    assert una == diez and una > 0


# --- 7.3 Borrador --------------------------------------------------------------------------------------------

async def test_put_en_borrador_recalcula_y_audita(session_factory, client: AsyncClient, esc, cat) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory, obra_social_id=cat["swiss"])
    pid = (await crear_presupuesto(client, esc.recepcion, paciente, (cat["limpieza"], 1))).json()["id"]
    resp = await client.put(_url(paciente, f"/{pid}"), json={"lineas": lineas((cat["limpieza"], 2))},
                            headers=bearer(esc.recepcion))
    assert resp.status_code == 200, resp.text
    assert resp.json()["total_paciente"] == "5000.00" and len(resp.json()["lineas"]) == 1
    assert len(await auditorias(session_factory, "edicion_presupuesto")) == 1
    assert len(await auditorias(session_factory, "alta_presupuesto")) == 1


async def test_put_sobre_un_presentado_es_409_no_editable(session_factory, client: AsyncClient, esc, cat) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory, obra_social_id=cat["swiss"])
    pid = (await crear_presupuesto(client, esc.recepcion, paciente, (cat["limpieza"], 1))).json()["id"]
    await transicionar(client, esc.recepcion, paciente, pid, "presentar")
    resp = await client.put(_url(paciente, f"/{pid}"), json={"lineas": lineas((cat["limpieza"], 9))},
                            headers=bearer(esc.recepcion))
    assert (resp.status_code, resp.json()["motivo"]) == (409, "presupuesto_no_editable")
    assert len(await auditorias(session_factory, "edicion_presupuesto")) == 0


async def test_sin_lineas_o_tratamiento_inexistente_422(session_factory, client: AsyncClient, esc, cat) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    h = bearer(esc.recepcion)
    assert (await client.post(_url(paciente), json={"lineas": []}, headers=h)).status_code == 422
    inexistente = await crear_presupuesto(client, esc.recepcion, paciente, (987654, 1))
    assert (inexistente.status_code, inexistente.json()["motivo"]) == (422, "tratamiento_inexistente")
    assert await contar(session_factory, "presupuesto") == 0


async def test_obra_social_inactiva_422_y_null_es_particular(session_factory, client: AsyncClient, esc, cat) -> None:  # type: ignore[no-untyped-def]
    inactiva = await crear_obra_social(session_factory, "VIEJA", "Prepaga Vieja", activa=False)
    paciente = await crear_paciente(session_factory, obra_social_id=cat["swiss"])
    mala = await crear_presupuesto(client, esc.recepcion, paciente, (cat["limpieza"], 1), obra_social_id=inactiva)
    assert (mala.status_code, mala.json()["motivo"]) == (422, "obra_social_inactiva")
    particular = await crear_presupuesto(client, esc.recepcion, paciente, (cat["limpieza"], 1), obra_social_id=None)
    assert particular.status_code == 201
    assert (particular.json()["obra_social"], particular.json()["total_paciente"]) == (None, "25000.00")
    otra = await crear_presupuesto(client, esc.recepcion, paciente, (cat["limpieza"], 1), obra_social_id=cat["omint"])
    assert otra.json()["total_paciente"] == "3750.00"  # 25000 al 85 %


async def test_paciente_inexistente_404_al_crear(client: AsyncClient, esc, cat) -> None:  # type: ignore[no-untyped-def]
    resp = await crear_presupuesto(client, esc.recepcion, 987654, (cat["limpieza"], 1))
    assert resp.status_code == 404


# --- 7.4 Estados y congelamiento -----------------------------------------------------------------------------

async def test_presentar_y_aceptar_dejan_las_fechas(session_factory, client: AsyncClient, esc, cat) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory, obra_social_id=cat["swiss"])
    pid = (await crear_presupuesto(client, esc.recepcion, paciente, (cat["limpieza"], 1))).json()["id"]
    presentado = await transicionar(client, esc.recepcion, paciente, pid, "presentar")
    assert presentado.status_code == 200 and presentado.json()["estado"] == "presentado"
    assert presentado.json()["presentado_en"] is not None and presentado.json()["resuelto_en"] is None
    aceptado_ = await transicionar(client, esc.recepcion, paciente, pid, "aceptar")
    assert aceptado_.json()["estado"] == "aceptado" and aceptado_.json()["resuelto_en"] is not None
    assert len(await auditorias(session_factory, "transicion_presupuesto")) == 2


@pytest.mark.parametrize("previas,accion", [([], "aceptar"), ([], "rechazar"), (["presentar", "rechazar"], "presentar"),
                                            (["presentar", "rechazar"], "aceptar"), (["presentar", "aceptar"], "rechazar"),
                                            (["presentar"], "presentar")])
async def test_transiciones_invalidas_409_sin_cambios(session_factory, client: AsyncClient, esc, cat,  # type: ignore[no-untyped-def]
                                                       previas: list[str], accion: str) -> None:
    paciente = await crear_paciente(session_factory, obra_social_id=cat["swiss"])
    pid = (await crear_presupuesto(client, esc.recepcion, paciente, (cat["limpieza"], 1))).json()["id"]
    for previa in previas:
        assert (await transicionar(client, esc.recepcion, paciente, pid, previa)).status_code == 200
    antes = len(await auditorias(session_factory, "transicion_presupuesto"))
    resp = await transicionar(client, esc.recepcion, paciente, pid, accion)
    assert (resp.status_code, resp.json()["motivo"]) == (409, "transicion_invalida")
    assert len(await auditorias(session_factory, "transicion_presupuesto")) == antes


async def test_anular_un_aceptado_con_pago_registrado_409_y_sin_pagos_ok(session_factory, client: AsyncClient, esc, cat) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory, obra_social_id=cat["swiss"])
    pid = await aceptado(client, esc.recepcion, paciente, (cat["limpieza"], 1))
    creado = await client.post(_url(paciente, f"/{pid}/pagos"), json={"medio": "transferencia", "monto": "1000.00"},
                               headers=bearer(esc.recepcion))
    assert creado.status_code == 201, creado.text
    pago = creado.json()["pago"]["id"]
    resp = await transicionar(client, esc.recepcion, paciente, pid, "anular", motivo="se cargó mal el plan")
    assert (resp.status_code, resp.json()["motivo"]) == (409, "presupuesto_con_pagos")
    # tras anular el pago por el endpoint, la anulación del presupuesto se acepta
    assert (await client.post(_url(paciente, f"/{pid}/pagos/{pago}/anular"), json={"motivo": "cargado dos veces"},
                              headers=bearer(esc.recepcion))).status_code == 200
    ok = await transicionar(client, esc.recepcion, paciente, pid, "anular", motivo="se cargó mal el plan")
    assert ok.status_code == 200 and ok.json()["estado"] == "anulado" and ok.json()["anulado_motivo"]


@pytest.mark.parametrize("motivo", ["ab", "", "m" * 301])
async def test_anular_exige_motivo_de_3_a_300(session_factory, client: AsyncClient, esc, cat, motivo: str) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    pid = (await crear_presupuesto(client, esc.recepcion, paciente, (cat["limpieza"], 1))).json()["id"]
    resp = await transicionar(client, esc.recepcion, paciente, pid, "anular", motivo=motivo)
    assert resp.status_code == 422


async def test_un_borrador_se_puede_anular(session_factory, client: AsyncClient, esc, cat) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    pid = (await crear_presupuesto(client, esc.recepcion, paciente, (cat["limpieza"], 1))).json()["id"]
    resp = await transicionar(client, esc.recepcion, paciente, pid, "anular", motivo="duplicado")
    assert resp.status_code == 200 and resp.json()["estado"] == "anulado"


async def test_cambiar_el_precio_despues_de_presentar_no_altera_el_presupuesto(session_factory, client: AsyncClient, esc, cat) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory, obra_social_id=cat["swiss"])
    pid = (await crear_presupuesto(client, esc.recepcion, paciente, (cat["limpieza"], 1))).json()["id"]
    await transicionar(client, esc.recepcion, paciente, pid, "presentar")
    async with session_factory() as s:
        await s.execute(update(Tratamiento).where(Tratamiento.id == cat["limpieza"]).values(
            precio_base=Decimal("30000.00")))
        await s.execute(update(Nomenclador).where(Nomenclador.tratamiento_id == cat["limpieza"]).values(
            cobertura_porcentaje=Decimal("10.00")))
        await s.commit()
    for token in (esc.recepcion, esc.admin):
        leido = (await client.get(_url(paciente, f"/{pid}"), headers=bearer(token))).json()
        assert (leido["lineas"][0]["importe_bruto"], leido["total_paciente"]) == ("25000.00", "2500.00")
    aceptar = await transicionar(client, esc.recepcion, paciente, pid, "aceptar")
    assert aceptar.json()["total_paciente"] == "2500.00"


async def test_cambia_el_nomenclador_con_un_borrador_abierto_se_aplica_al_presentar(session_factory, client: AsyncClient, esc, cat) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory, obra_social_id=cat["swiss"])
    borrador = (await crear_presupuesto(client, esc.recepcion, paciente, (cat["limpieza"], 1))).json()
    assert borrador["lineas"][0]["cobertura_porcentaje"] == "90.00"
    async with session_factory() as s:
        await s.execute(update(Nomenclador).where(Nomenclador.tratamiento_id == cat["limpieza"],
                                                  Nomenclador.obra_social_id == cat["swiss"]).values(
            cobertura_porcentaje=Decimal("80.00")))
        await s.commit()
    presentado = (await transicionar(client, esc.recepcion, paciente, borrador["id"], "presentar")).json()
    assert (presentado["lineas"][0]["cobertura_porcentaje"], presentado["total_paciente"]) == ("80.00", "5000.00")


# --- 7.5 La odontóloga no escribe presupuestos (O4) ----------------------------------------------------------

async def test_la_odontologa_propia_recibe_403_en_toda_escritura(session_factory, client: AsyncClient, esc, cat) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory, obra_social_id=cat["swiss"])
    await turno_de(session_factory, esc, paciente, hace(dias=30))
    pid = (await crear_presupuesto(client, esc.recepcion, paciente, (cat["limpieza"], 1))).json()["id"]
    antes = len(await auditorias(session_factory))
    h = bearer(esc.ana)
    assert (await client.post(_url(paciente), json={"lineas": lineas((cat["limpieza"], 1))}, headers=h)).status_code == 403
    assert (await client.put(_url(paciente, f"/{pid}"), json={"lineas": lineas((cat["limpieza"], 3))},
                             headers=h)).status_code == 403
    for accion, cuerpo in (("presentar", {}), ("aceptar", {}), ("rechazar", {}), ("anular", {"motivo": "no corresponde"})):
        resp = await client.post(_url(paciente, f"/{pid}/{accion}"), json=cuerpo, headers=h)
        assert resp.status_code == 403, accion
    assert len(await auditorias(session_factory)) == antes
    assert await contar(session_factory, "presupuesto") == 1


async def test_la_odontologa_recibe_403_y_no_404_sobre_un_paciente_inexistente(client: AsyncClient, esc, cat) -> None:  # type: ignore[no-untyped-def]
    resp = await client.post(_url(987654), json={"lineas": lineas((cat["limpieza"], 1))}, headers=bearer(esc.ana))
    assert resp.status_code == 403


# --- 7.6 Consulta por rol ------------------------------------------------------------------------------------

async def test_la_odontologa_lee_sin_pagos_ni_saldo_y_queda_auditado(session_factory, client: AsyncClient, esc, cat) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory, obra_social_id=cat["swiss"])
    await turno_de(session_factory, esc, paciente, hace(dias=30))
    pid = await aceptado(client, esc.recepcion, paciente, (cat["limpieza"], 1))
    await insertar_pago(session_factory, pid, "500.00", hace(dias=1))
    h = bearer(esc.ana)
    lista = await client.get(_url(paciente), headers=h)
    detalle = await client.get(_url(paciente, f"/{pid}"), headers=h)
    assert lista.status_code == 200 and detalle.status_code == 200
    for cuerpo in (lista.json()[0], detalle.json()):
        assert not {"pagos", "total_pagado", "saldo"} & set(cuerpo)
        assert cuerpo["total_paciente"] == "2500.00" and len(cuerpo["lineas"]) == 1
    assert len(await auditorias(session_factory, "lectura_presupuesto")) == 2
    completo = (await client.get(_url(paciente, f"/{pid}"), headers=bearer(esc.recepcion))).json()
    assert (completo["total_pagado"], completo["saldo"], len(completo["pagos"])) == ("500.00", "2000.00", 1)


@pytest.mark.parametrize("estado", ["reservado", "confirmado"])
async def test_odontologa_ajena_por_turno_sin_atender_403(session_factory, client: AsyncClient, esc, cat, estado: str) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    await turno_de(session_factory, esc, paciente, AHORA + timedelta(days=2), estado)
    resp = await client.get(_url(paciente), headers=bearer(esc.ana))
    assert (resp.status_code, resp.json()["motivo"]) == (403, "paciente_ajeno")


async def test_odontologa_ajena_por_atencion_de_otra_profesional_403(session_factory, client: AsyncClient, esc, cat) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    await turno_de(session_factory, esc, paciente, hace(dias=20), "atendido", prof="bruno")
    assert (await client.get(_url(paciente), headers=bearer(esc.ana))).status_code == 403
    assert await auditorias(session_factory, "lectura_presupuesto") == []


async def test_presupuesto_de_otro_paciente_pedido_por_la_ruta_de_este_404(session_factory, client: AsyncClient, esc, cat) -> None:  # type: ignore[no-untyped-def]
    a = await crear_paciente(session_factory)
    b = await crear_paciente(session_factory, nombre="Mateo", apellido="Prueba")
    pid_b = (await crear_presupuesto(client, esc.recepcion, b, (cat["limpieza"], 1))).json()["id"]
    resp = await client.get(_url(a, f"/{pid_b}"), headers=bearer(esc.recepcion))
    assert resp.status_code == 404
    assert (await transicionar(client, esc.recepcion, a, pid_b, "presentar")).status_code == 404


async def test_aceptar_no_llama_a_ningun_servicio_externo_ni_devuelve_comprobante(session_factory, client: AsyncClient, esc, cat, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory, obra_social_id=cat["swiss"])
    pid = (await crear_presupuesto(client, esc.recepcion, paciente, (cat["limpieza"], 1))).json()["id"]
    await transicionar(client, esc.recepcion, paciente, pid, "presentar")
    externas: list[str] = []
    original = httpx.AsyncClient.send

    async def _espia(self: httpx.AsyncClient, request: httpx.Request, **kwargs: object) -> httpx.Response:
        if request.url.host != "test":  # "test" es el cliente ASGI de este mismo test (sin red)
            externas.append(str(request.url))
            raise AssertionError("no debe haber llamadas externas de facturación")
        return await original(self, request, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(httpx.AsyncClient, "send", _espia)
    resp = await transicionar(client, esc.recepcion, paciente, pid, "aceptar")
    assert resp.status_code == 200 and externas == []
    assert not {"comprobante", "numero_comprobante", "cae", "factura"} & set(resp.json())


async def test_pedir_factura_al_presentar_es_422(session_factory, client: AsyncClient, esc, cat) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    pid = (await crear_presupuesto(client, esc.recepcion, paciente, (cat["limpieza"], 1))).json()["id"]
    resp = await transicionar(client, esc.recepcion, paciente, pid, "presentar", emitir_factura=True)
    assert resp.status_code == 422
    assert (await client.get(_url(paciente, f"/{pid}"), headers=bearer(esc.recepcion))).json()["estado"] == "borrador"


async def test_total_cero_se_presenta_y_acepta(session_factory, client: AsyncClient, esc, cat) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory, obra_social_id=cat["osde"])  # OSDE cubre el 100 %
    pid = await aceptado(client, esc.recepcion, paciente, (cat["consulta"], 1))
    cuerpo = (await client.get(_url(paciente, f"/{pid}"), headers=bearer(esc.recepcion))).json()
    assert (cuerpo["estado"], cuerpo["total_paciente"], cuerpo["saldo"]) == ("aceptado", "0.00", "0.00")


async def test_la_lista_se_devuelve_del_mas_reciente_al_mas_antiguo(session_factory, client: AsyncClient, esc, cat) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory)
    primero = (await crear_presupuesto(client, esc.recepcion, paciente, (cat["limpieza"], 1))).json()["id"]
    segundo = (await crear_presupuesto(client, esc.recepcion, paciente, (cat["consulta"], 1))).json()["id"]
    lista = (await client.get(_url(paciente), headers=bearer(esc.recepcion))).json()
    assert [p["id"] for p in lista] == [segundo, primero]
