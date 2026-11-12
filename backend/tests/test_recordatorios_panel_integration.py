"""C-09 (8.1-8.4): API del panel para recordatorios (listado, enviado, fallido) y su RBAC. Datos sintéticos (R19)."""

from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import select

from app.models.core import RegistroAuditoria
from tests.clinica_helpers import Escenario, crear_paciente, sembrar_escenario
from tests.conftest import bearer
from tests.panel_helpers import TELEFONO, insertar_turno, local
from tests.recordatorios_helpers import AHORA, poner_turno, recordatorios, sembrar_recordatorio

URL = "/api/panel/recordatorios"


@pytest.fixture
async def esc(session_factory, reloj) -> Escenario:  # type: ignore[no-untyped-def]
    reloj(AHORA)
    return await sembrar_escenario(session_factory)


async def _turno_con_recordatorio(factory, esc: Escenario, horas: float, estado: str = "pendiente", *,  # type: ignore[no-untyped-def]
                                  prof: str = "ana", sillon: str = "s1", **turno):
    inicio = AHORA + timedelta(hours=horas)
    turno_id = await insertar_turno(factory, esc.mundo, inicio, prof=prof, sillon=sillon, **turno)
    rid = await sembrar_recordatorio(factory, turno_id, inicio, estado)
    return turno_id, rid, inicio


def _texto(link: str) -> str:
    return parse_qs(urlsplit(link).query)["text"][0]


# --- 8.1 Listado ------------------------------------------------------------------------------------------------

async def test_recepcion_ve_los_pendientes_ordenados_por_inicio_con_su_link(client, session_factory, esc) -> None:  # type: ignore[no-untyped-def]
    _, r116, _ = await _turno_con_recordatorio(session_factory, esc, 26)  # 09:00 de mañana
    _, r117, _ = await _turno_con_recordatorio(session_factory, esc, 25, sillon="s2", prof="bruno")
    r = await client.get(URL, headers=bearer(esc.recepcion))
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert [i["id"] for i in items] == [r117, r116]
    primero = items[0]
    assert primero["estado"] == "pendiente" and primero["profesional"] == "Dr. Bruno Ejemplo"
    assert primero["contacto_nombre"] == "Carlos Sintético" and primero["tratamiento"] == "Limpieza dental"
    assert primero["turno_inicio"].endswith("-03:00")
    assert primero["link"].startswith("https://wa.me/5491144445555?text=")
    mensaje = _texto(primero["link"])
    assert "Carlos Sintético" in mensaje and "/confirmar#" in mensaje and "/gestionar#" in mensaje
    assert "Dr. Bruno Ejemplo" in mensaje and "Limpieza dental" in mensaje


async def test_admin_tambien_lista(client, session_factory, esc) -> None:  # type: ignore[no-untyped-def]
    await _turno_con_recordatorio(session_factory, esc, 26)
    assert (await client.get(URL, headers=bearer(esc.admin))).status_code == 200


async def test_la_odontologa_recibe_403_sin_telefonos_y_sin_sesion_401(client, session_factory, esc) -> None:  # type: ignore[no-untyped-def]
    await _turno_con_recordatorio(session_factory, esc, 26)
    r = await client.get(URL, headers=bearer(esc.ana))
    assert r.status_code == 403 and TELEFONO.removeprefix("+") not in r.text and "wa.me" not in r.text
    r = await client.get(URL)
    assert r.status_code == 401 and "wa.me" not in r.text


async def test_un_recordatorio_del_horario_anterior_no_aparece_aunque_el_trabajo_no_corrio(  # type: ignore[no-untyped-def]
        client, session_factory, esc) -> None:
    turno, _, inicio = await _turno_con_recordatorio(session_factory, esc, 26)
    await poner_turno(session_factory, turno, inicio=inicio + timedelta(hours=2), fin=inicio + timedelta(hours=2, minutes=30))
    assert (await client.get(URL, headers=bearer(esc.recepcion))).json()["items"] == []


@pytest.mark.parametrize("estado_turno", ["cancelado", "ausente", "atendido", "en_espera"])
async def test_un_turno_que_dejo_de_ser_reservado_o_confirmado_no_aparece(  # type: ignore[no-untyped-def]
        client, session_factory, esc, estado_turno: str) -> None:
    turno, _, _ = await _turno_con_recordatorio(session_factory, esc, 26)
    extra = {"en_espera_vence_en": AHORA + timedelta(hours=26)} if estado_turno == "en_espera" else {}
    await poner_turno(session_factory, turno, estado=estado_turno, **extra)
    assert (await client.get(URL, headers=bearer(esc.recepcion))).json()["items"] == []


async def test_solo_aparecen_los_que_empiezan_dentro_de_la_anticipacion_y_aun_no_empezaron(  # type: ignore[no-untyped-def]
        client, session_factory, esc) -> None:
    await _turno_con_recordatorio(session_factory, esc, 60)  # fuera de las 48 h
    await _turno_con_recordatorio(session_factory, esc, -1, sillon="s2", prof="bruno")  # ya empezó
    dentro, rid, _ = await _turno_con_recordatorio(session_factory, esc, 47.9, prof="bruno")
    assert [i["id"] for i in (await client.get(URL, headers=bearer(esc.recepcion))).json()["items"]] == [rid]


async def test_por_defecto_pendientes_y_fallidos_y_el_filtro_por_estado(client, session_factory, esc) -> None:  # type: ignore[no-untyped-def]
    ids: dict[str, int] = {}
    for n, estado in enumerate(("pendiente", "fallido", "enviado", "confirmado")):
        _, ids[estado], _ = await _turno_con_recordatorio(session_factory, esc, 20 + n, estado,
                                                          sillon="s1" if n % 2 == 0 else "s2")
    h = bearer(esc.recepcion)
    por_defecto = {i["estado"] for i in (await client.get(URL, headers=h)).json()["items"]}
    assert por_defecto == {"pendiente", "fallido"}
    solo = (await client.get(URL, params={"estado": "enviado"}, headers=h)).json()["items"]
    assert [i["id"] for i in solo] == [ids["enviado"]]
    varios = (await client.get(URL, params=[("estado", "enviado"), ("estado", "confirmado")], headers=h)).json()["items"]
    assert {i["estado"] for i in varios} == {"enviado", "confirmado"}
    assert [i for i in varios if i["estado"] == "confirmado"][0]["link"] is None  # ya no corresponde abrir WhatsApp
    assert (await client.get(URL, params={"estado": "anulado"}, headers=h)).status_code == 422


async def test_un_fallido_sin_telefono_se_ve_sin_link_y_con_su_motivo(client, session_factory, esc) -> None:  # type: ignore[no-untyped-def]
    inicio = AHORA + timedelta(hours=26)
    turno = await insertar_turno(session_factory, esc.mundo, inicio, telefono=None, nombre=None)
    await sembrar_recordatorio(session_factory, turno, inicio, "fallido", motivo="sin_telefono")
    [item] = (await client.get(URL, headers=bearer(esc.recepcion))).json()["items"]
    assert (item["estado"], item["motivo"], item["link"]) == ("fallido", "sin_telefono", None)


async def test_el_telefono_de_la_ficha_se_usa_si_el_turno_no_tiene(client, session_factory, esc) -> None:  # type: ignore[no-untyped-def]
    paciente = await crear_paciente(session_factory, nombre="Lucía", apellido="Ficticia", telefono="+5491100000002")
    inicio = AHORA + timedelta(hours=26)
    turno = await insertar_turno(session_factory, esc.mundo, inicio, telefono=None, nombre=None, paciente_id=paciente)
    await sembrar_recordatorio(session_factory, turno, inicio)
    [item] = (await client.get(URL, headers=bearer(esc.recepcion))).json()["items"]
    assert item["link"].startswith("https://wa.me/5491100000002?text=")
    assert "Lucía" in _texto(item["link"])


async def test_un_turno_interno_sin_codigo_arma_el_mensaje_sin_enlaces(client, session_factory, esc) -> None:  # type: ignore[no-untyped-def]
    inicio = AHORA + timedelta(hours=26)
    turno = await insertar_turno(session_factory, esc.mundo, inicio, con_codigo=False, origen="manual")
    await sembrar_recordatorio(session_factory, turno, inicio)
    [item] = (await client.get(URL, headers=bearer(esc.recepcion))).json()["items"]
    assert "/confirmar#" not in _texto(item["link"]) and "/gestionar#" not in _texto(item["link"])


# --- 8.3 Marcar enviado ----------------------------------------------------------------------------------------

async def test_abrir_whatsapp_marca_enviado_con_usuario_y_fecha_y_audita_sin_pii(client, session_factory, esc) -> None:  # type: ignore[no-untyped-def]
    turno, rid, _ = await _turno_con_recordatorio(session_factory, esc, 26)
    r = await client.post(f"{URL}/{rid}/enviado", headers=bearer(esc.recepcion))
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "enviado"
    [rec] = await recordatorios(session_factory, turno)
    assert (rec.estado, rec.enviado_por_usuario_id, rec.enviado_en) == ("enviado", esc.recepcion_id, AHORA)
    async with session_factory() as s:
        [aud] = (await s.execute(select(RegistroAuditoria).where(
            RegistroAuditoria.entidad == "recordatorio", RegistroAuditoria.entidad_id == str(rid)))).scalars().all()
    assert aud.usuario_id == esc.recepcion_id
    assert (aud.datos_antes["estado"], aud.datos_despues["estado"]) == ("pendiente", "enviado")
    contenido = f"{aud.datos_antes} {aud.datos_despues}"
    for prohibido in ("5491144445555", "wa.me", "Carlos", "CODIGO", "confirmar#"):
        assert prohibido not in contenido


@pytest.mark.parametrize("estado,motivo", [("anulado", "turno_cancelado"), ("confirmado", None)])
async def test_marcar_enviado_un_anulado_o_confirmado_es_409_y_no_cambia(client, session_factory, esc, estado, motivo) -> None:  # type: ignore[no-untyped-def]
    inicio = AHORA + timedelta(hours=26)
    turno = await insertar_turno(session_factory, esc.mundo, inicio)
    rid = await sembrar_recordatorio(session_factory, turno, inicio, estado)
    r = await client.post(f"{URL}/{rid}/enviado", headers=bearer(esc.recepcion))
    assert r.status_code == 409 and r.json()["motivo"] == "recordatorio_no_vigente"
    [rec] = await recordatorios(session_factory, turno)
    assert rec.estado == estado


async def test_marcar_enviado_un_recordatorio_de_otro_horario_es_409(client, session_factory, esc) -> None:  # type: ignore[no-untyped-def]
    turno, rid, inicio = await _turno_con_recordatorio(session_factory, esc, 26)
    await poner_turno(session_factory, turno, inicio=inicio + timedelta(hours=3), fin=inicio + timedelta(hours=3, minutes=30))
    r = await client.post(f"{URL}/{rid}/enviado", headers=bearer(esc.recepcion))
    assert r.status_code == 409 and r.json()["motivo"] == "recordatorio_no_vigente"


async def test_reenviar_un_enviado_es_200_y_actualiza_la_fecha(client, session_factory, esc, reloj) -> None:  # type: ignore[no-untyped-def]
    inicio = AHORA + timedelta(hours=26)
    turno = await insertar_turno(session_factory, esc.mundo, inicio)
    rid = await sembrar_recordatorio(session_factory, turno, inicio, "enviado", enviado_en=AHORA - timedelta(days=1))
    r = await client.post(f"{URL}/{rid}/enviado", headers=bearer(esc.recepcion))
    assert r.status_code == 200
    [rec] = await recordatorios(session_factory, turno)
    assert (rec.estado, rec.enviado_en) == ("enviado", AHORA)


async def test_marcar_un_fallido_como_enviado_lo_rescata(client, session_factory, esc) -> None:  # type: ignore[no-untyped-def]
    turno, rid, _ = await _turno_con_recordatorio(session_factory, esc, 26, "fallido")
    assert (await client.post(f"{URL}/{rid}/enviado", headers=bearer(esc.recepcion))).status_code == 200
    [rec] = await recordatorios(session_factory, turno)
    assert (rec.estado, rec.motivo) == ("enviado", None)


@pytest.mark.parametrize("accion,cuerpo", [("enviado", None), ("fallido", {"motivo": "otro"})])
async def test_un_recordatorio_inexistente_es_404(client, session_factory, esc, accion, cuerpo) -> None:  # type: ignore[no-untyped-def]
    r = await client.post(f"{URL}/999999/{accion}", json=cuerpo, headers=bearer(esc.recepcion))
    assert r.status_code == 404 and r.json()["motivo"] == "recordatorio_inexistente"


# --- Marcar fallido ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("motivo", ["numero_invalido", "sin_whatsapp", "otro"])
async def test_no_se_pudo_enviar_deja_fallido_con_el_motivo_y_visible(client, session_factory, esc, motivo) -> None:  # type: ignore[no-untyped-def]
    turno, rid, _ = await _turno_con_recordatorio(session_factory, esc, 26)
    r = await client.post(f"{URL}/{rid}/fallido", json={"motivo": motivo}, headers=bearer(esc.recepcion))
    assert r.status_code == 200, r.text
    [rec] = await recordatorios(session_factory, turno)
    assert (rec.estado, rec.motivo) == ("fallido", motivo)
    [item] = (await client.get(URL, headers=bearer(esc.recepcion))).json()["items"]
    assert (item["estado"], item["motivo"]) == ("fallido", motivo)
    async with session_factory() as s:
        [aud] = (await s.execute(select(RegistroAuditoria).where(
            RegistroAuditoria.entidad == "recordatorio", RegistroAuditoria.entidad_id == str(rid)))).scalars().all()
    assert aud.datos_despues["motivo"] == motivo and aud.datos_despues["estado"] == "fallido"


async def test_marcar_fallido_un_enviado_conserva_la_fecha_de_envio(client, session_factory, esc) -> None:  # type: ignore[no-untyped-def]
    inicio = AHORA + timedelta(hours=26)
    turno = await insertar_turno(session_factory, esc.mundo, inicio)
    rid = await sembrar_recordatorio(session_factory, turno, inicio, "enviado")
    assert (await client.post(f"{URL}/{rid}/fallido", json={"motivo": "sin_whatsapp"},
                              headers=bearer(esc.recepcion))).status_code == 200
    [rec] = await recordatorios(session_factory, turno)
    assert rec.estado == "fallido" and rec.enviado_en is not None


@pytest.mark.parametrize("estado", ["confirmado", "anulado"])
async def test_marcar_fallido_un_confirmado_o_anulado_es_409(client, session_factory, esc, estado) -> None:  # type: ignore[no-untyped-def]
    inicio = AHORA + timedelta(hours=26)
    turno = await insertar_turno(session_factory, esc.mundo, inicio)
    rid = await sembrar_recordatorio(session_factory, turno, inicio, estado)
    r = await client.post(f"{URL}/{rid}/fallido", json={"motivo": "otro"}, headers=bearer(esc.recepcion))
    assert r.status_code == 409 and r.json()["motivo"] == "recordatorio_no_vigente"
    [rec] = await recordatorios(session_factory, turno)
    assert rec.estado == estado


@pytest.mark.parametrize("cuerpo", [{"motivo": "no atiende"}, {"motivo": "sin_telefono"}, {"motivo": "turno_cancelado"},
                                    {}, {"motivo": "otro", "extra": 1}])
async def test_un_motivo_fuera_de_la_lista_es_422_y_no_cambia(client, session_factory, esc, cuerpo) -> None:  # type: ignore[no-untyped-def]
    turno, rid, _ = await _turno_con_recordatorio(session_factory, esc, 26)
    r = await client.post(f"{URL}/{rid}/fallido", json=cuerpo, headers=bearer(esc.recepcion))
    assert r.status_code == 422
    [rec] = await recordatorios(session_factory, turno)
    assert rec.estado == "pendiente"


# --- 8.4 RBAC: ruta x actor -------------------------------------------------------------------------------------

@pytest.mark.parametrize("actor,esperado", [("recepcion", 200), ("admin", 200), ("odontologa", 403), ("sin_token", 401)])
@pytest.mark.parametrize("ruta", ["listado", "enviado", "fallido"])
async def test_matriz_de_roles_de_los_tres_endpoints(client, session_factory, esc, ruta, actor, esperado) -> None:  # type: ignore[no-untyped-def]
    _, rid, _ = await _turno_con_recordatorio(session_factory, esc, 26)
    token = {"recepcion": esc.recepcion, "admin": esc.admin, "odontologa": esc.ana, "sin_token": None}[actor]
    h = {} if token is None else bearer(token)
    if ruta == "listado":
        r = await client.get(URL, headers=h)
    elif ruta == "enviado":
        r = await client.post(f"{URL}/{rid}/enviado", headers=h)
    else:
        r = await client.post(f"{URL}/{rid}/fallido", json={"motivo": "otro"}, headers=h)
    assert r.status_code == esperado, r.text
    if esperado in (401, 403):
        assert set(r.json()) == {"detail"}
        [rec] = await recordatorios(session_factory)
        assert rec.estado == "pendiente"
