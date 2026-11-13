"""C-13 (8.1, 8.2, D9, O7, O8, O11-O13): ``GET /api/panel/export`` — CSV, permisos, fórmulas y auditoría. Sintético (R19)."""

import asyncio
import csv
import io
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import select, update

from app.caja.models import CierreCaja
from app.models.core import Paciente, RegistroAuditoria
from tests.clinica_helpers import Escenario, crear_obra_social, crear_paciente, sembrar_escenario
from tests.conftest import bearer
from tests.panel_helpers import insertar_turno, local

URL = "/api/panel/export"
AHORA = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)  # 09:00 del 2026-11-13 en la clínica
SEMANA = (date(2026, 11, 16), date(2026, 11, 20))
BOM = b"\xef\xbb\xbf"


@pytest.fixture
async def esc(session_factory, reloj) -> Escenario:  # type: ignore[no-untyped-def]
    reloj(AHORA)
    return await sembrar_escenario(session_factory)


async def exportar(client: AsyncClient, token: str, **params: Any) -> Response:
    return await client.get(URL, params={"formato": "csv", **params}, headers=bearer(token))


def filas(r: Response) -> list[list[str]]:
    return list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"), newline="")))


async def registros(factory, accion: str = "exportacion") -> list[RegistroAuditoria]:  # type: ignore[no-untyped-def]
    async with factory() as s:
        return list((await s.execute(select(RegistroAuditoria).where(RegistroAuditoria.accion == accion)
                                     .order_by(RegistroAuditoria.id))).scalars())


async def cierre(factory, dia: date, *, estado: str = "vigente", neto: str = "0.00", motivo: str | None = None,  # type: ignore[no-untyped-def]
                 observaciones: str | None = None) -> int:
    async with factory() as s:
        c = CierreCaja(dia=dia, estado=estado, total_ingresos=Decimal(neto), total_egresos=Decimal("0.00"),
                       total_neto=Decimal(neto), observaciones=observaciones,
                       anulado_en=AHORA if estado == "anulado" else None, anulado_motivo=motivo)
        s.add(c)
        await s.flush()
        await s.commit()
        return int(c.id)


# --- Turnos ---------------------------------------------------------------------------------------------------------

async def test_turnos_de_una_semana_traen_encabezado_mas_tres_filas_con_desfase_y_sin_codigo_de_gestion(
        session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await insertar_turno(session_factory, esc.mundo, local(date(2026, 11, 16), "09:00"), nombre="Lucía Ejemplo",
                         telefono="+5491100000001")
    await insertar_turno(session_factory, esc.mundo, local(date(2026, 11, 18), "10:00"), nombre="Mateo Prueba",
                         telefono="+5491100000002")
    await insertar_turno(session_factory, esc.mundo, local(date(2026, 11, 20), "23:30"), nombre=None, telefono=None)
    await insertar_turno(session_factory, esc.mundo, local(date(2026, 11, 25), "09:00"))
    r = await exportar(client, esc.recepcion, entidad="turnos", desde="2026-11-16", hasta="2026-11-20")
    assert r.status_code == 200, r.text
    tabla = filas(r)
    assert len(tabla) == 4 and tabla[0][:4] == ["id", "inicio", "fin", "estado"]
    assert "codigo_gestion" not in tabla[0] and not any("codigo" in c for c in tabla[0])
    por_columna = dict(zip(tabla[0], tabla[1]))
    assert por_columna["inicio"] == "2026-11-16T09:00:00-03:00" and por_columna["fin"] == "2026-11-16T09:30:00-03:00"
    assert (por_columna["contacto_nombre"], por_columna["contacto_telefono"]) == ("Lucía Ejemplo", "+5491100000001")
    assert por_columna["profesional"] and por_columna["sillon"] and por_columna["tratamiento"]
    ultima = dict(zip(tabla[0], tabla[3]))
    assert ultima["inicio"] == "2026-11-20T23:30:00-03:00" and ultima["contacto_nombre"] == ""  # el último día entero


async def test_entidad_o_formato_no_soportados_dan_422_con_los_valores_validos_y_ningun_archivo(
        session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    r = await exportar(client, esc.recepcion, entidad="fichas")
    assert r.status_code == 422 and "turnos" in r.text and "pacientes" in r.text and "cierres_caja" in r.text
    assert "csv" in (await client.get(URL, params={"entidad": "turnos", "formato": "xlsx"},
                                      headers=bearer(esc.recepcion))).text
    assert (await exportar(client, esc.recepcion, entidad="turnos", desde="2026-11-20", hasta="2026-11-16")
            ).status_code == 422
    assert (await client.get(URL, params={"entidad": "turnos"}, headers=bearer(esc.recepcion))).status_code == 422
    assert await registros(session_factory) == []


async def test_un_rango_sin_turnos_devuelve_solo_el_encabezado(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    r = await exportar(client, esc.recepcion, entidad="turnos", desde="2030-01-01", hasta="2030-01-31")
    assert r.status_code == 200 and len(filas(r)) == 1
    assert r.content.count(b"\r\n") == 1


async def test_sin_rango_se_exportan_todos_los_turnos_en_orden_de_inicio(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    for d in (date(2026, 11, 25), date(2026, 11, 16)):
        await insertar_turno(session_factory, esc.mundo, local(d, "09:00"))
    inicios = [f[1] for f in filas(await exportar(client, esc.admin, entidad="turnos"))[1:]]
    assert inicios == ["2026-11-16T09:00:00-03:00", "2026-11-25T09:00:00-03:00"]


# --- Pacientes ------------------------------------------------------------------------------------------------------

@pytest.fixture
async def dos(session_factory, esc) -> dict[str, int]:  # type: ignore[no-untyped-def]
    os_id = await crear_obra_social(session_factory, "SINT", "Obra Social Sintética")
    lucia = await crear_paciente(session_factory, nombre="Lucía", apellido="Ejemplo", dni="99000001",
                                 telefono="+5491100000011", obra_social_id=os_id, numero_afiliado="AF-001")
    mateo = await crear_paciente(session_factory, nombre="Mateo", apellido="Prueba", dni="99000002",
                                 telefono="+5491100000012")
    async with session_factory() as s:
        await s.execute(update(Paciente).where(Paciente.id == mateo).values(is_active=False))
        await s.commit()
    return {"lucia": lucia, "mateo": mateo}


async def test_el_admin_exporta_solo_los_pacientes_activos_sin_columnas_clinicas(
        session_factory, client: AsyncClient, esc, dos) -> None:  # type: ignore[no-untyped-def]
    r = await exportar(client, esc.admin, entidad="pacientes")
    assert r.status_code == 200
    tabla = filas(r)
    assert len(tabla) == 2
    fila = dict(zip(tabla[0], tabla[1]))
    assert (fila["nombre"], fila["apellido"], fila["dni"], fila["telefono"], fila["obra_social"],
            fila["numero_afiliado"], fila["activo"]) == ("Lucía", "Ejemplo", "99000001", "+5491100000011",
                                                         "Obra Social Sintética", "AF-001", "true")
    assert fila["creado_en"].endswith("-03:00")
    assert not {"alergias", "medicacion", "antecedentes_medicos", "observaciones"} & set(tabla[0])


async def test_recepcion_y_odontologa_no_exportan_pacientes_y_no_queda_registro(
        session_factory, client: AsyncClient, esc, dos) -> None:  # type: ignore[no-untyped-def]
    for token in (esc.recepcion, esc.ana):
        r = await exportar(client, token, entidad="pacientes")
        assert r.status_code == 403 and "99000001" not in r.text and not r.content.startswith(BOM)
    assert await registros(session_factory) == []


async def test_incluir_inactivos_suma_la_fila_de_mateo_con_activo_false(session_factory, client: AsyncClient, esc, dos) -> None:  # type: ignore[no-untyped-def]
    tabla = filas(await exportar(client, esc.admin, entidad="pacientes", incluir_inactivos="true"))
    assert len(tabla) == 3
    assert {dict(zip(tabla[0], f))["nombre"]: dict(zip(tabla[0], f))["activo"] for f in tabla[1:]} == {
        "Lucía": "true", "Mateo": "false"}


# --- Cierres de caja ------------------------------------------------------------------------------------------------

async def test_los_cierres_del_mes_traen_los_totales_exactos(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await cierre(session_factory, date(2026, 11, 2), neto="15000.00")
    await cierre(session_factory, date(2026, 11, 3), neto="0.00")
    await cierre(session_factory, date(2026, 10, 30), neto="999.00")
    tabla = filas(await exportar(client, esc.recepcion, entidad="cierres_caja", desde="2026-11-01", hasta="2026-11-30"))
    assert len(tabla) == 3
    datos = [dict(zip(tabla[0], f)) for f in tabla[1:]]
    assert [(d["dia"], d["total_neto"], d["total_ingresos"], d["total_egresos"], d["estado"]) for d in datos] == [
        ("2026-11-02", "15000.00", "15000.00", "0.00", "vigente"), ("2026-11-03", "0.00", "0.00", "0.00", "vigente")]


async def test_la_odontologa_no_exporta_nada(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    for entidad in ("turnos", "cierres_caja", "pacientes"):
        r = await exportar(client, esc.ana, entidad=entidad)
        assert r.status_code == 403 and not r.content.startswith(BOM)
    assert (await client.get(URL, params={"entidad": "turnos", "formato": "csv"})).status_code == 401
    assert await registros(session_factory) == []


async def test_un_dia_con_cierre_anulado_y_uno_vigente_exporta_las_dos_filas_con_el_motivo_escapado(
        session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    dia = date(2026, 11, 4)
    await cierre(session_factory, dia, estado="anulado", neto="100.00", motivo='Error de carga, "duplicado"')
    await cierre(session_factory, dia, neto="120.00")
    r = await exportar(client, esc.recepcion, entidad="cierres_caja", desde="2026-11-04", hasta="2026-11-04")
    assert '"Error de carga, ""duplicado"""' in r.content.decode("utf-8")
    tabla = filas(r)
    assert [dict(zip(tabla[0], f))["estado"] for f in tabla[1:]] == ["anulado", "vigente"]
    assert dict(zip(tabla[0], tabla[1]))["anulado_motivo"] == 'Error de carga, "duplicado"'
    assert all(len(f) == len(tabla[0]) for f in tabla)


# --- Formato --------------------------------------------------------------------------------------------------------

async def test_acentos_y_enies_se_leen_bien_y_el_archivo_declara_utf8_con_bom(
        session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    await crear_paciente(session_factory, nombre="Iñaki", apellido="Muñoz Ejemplo", dni="99000003")
    r = await exportar(client, esc.admin, entidad="pacientes")
    assert r.content.startswith(BOM) and BOM not in r.content[3:]
    assert filas(r)[1][1:3] == ["Iñaki", "Muñoz Ejemplo"]
    assert r.headers["content-type"] == "text/csv; charset=utf-8"


async def test_los_encabezados_de_la_descarga(session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    r = await exportar(client, esc.recepcion, entidad="turnos")
    assert r.headers["content-disposition"] == 'attachment; filename="turnos_2026-11-13.csv"'
    assert r.headers["cache-control"] == "no-store" and r.headers["x-content-type-options"] == "nosniff"
    r = await exportar(client, esc.recepcion, entidad="cierres_caja")
    assert r.headers["content-disposition"] == 'attachment; filename="cierres_caja_2026-11-13.csv"'


# --- Fórmulas -------------------------------------------------------------------------------------------------------

async def test_un_nombre_de_contacto_malicioso_llega_con_apostrofo_y_el_telefono_e164_intacto(
        session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    malicioso = '=HYPERLINK("http://example.invalid","ver")'
    await insertar_turno(session_factory, esc.mundo, local(date(2026, 11, 16), "09:00"), nombre=malicioso,
                         telefono="+5491100000001")
    tabla = filas(await exportar(client, esc.recepcion, entidad="turnos"))
    fila = dict(zip(tabla[0], tabla[1]))
    assert fila["contacto_nombre"] == "'" + malicioso
    assert fila["contacto_telefono"] == "+5491100000001"


@pytest.mark.parametrize("inicio", ["+", "-", "@", "\t"])
async def test_las_cuatro_variantes_de_inicio_peligroso_llevan_apostrofo(
        session_factory, client: AsyncClient, esc, inicio: str) -> None:  # type: ignore[no-untyped-def]
    await insertar_turno(session_factory, esc.mundo, local(date(2026, 11, 16), "09:00"), nombre=f"{inicio}cmd|calc")
    fila = dict(zip(*filas(await exportar(client, esc.recepcion, entidad="turnos"))))
    assert fila["contacto_nombre"] == f"'{inicio}cmd|calc"


# --- Auditoría de la exportación (8.2) ------------------------------------------------------------------------------

async def test_la_exportacion_deja_su_registro_con_usuario_ip_filtros_y_filas_sin_datos_personales(
        session_factory, esc, dos) -> None:  # type: ignore[no-untyped-def]
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app, client=("203.0.113.20", 4000)), base_url="https://test") as c:
        r = await exportar(c, esc.admin, entidad="pacientes", incluir_inactivos="true")
    assert r.status_code == 200
    [registro] = await registros(session_factory)
    assert (registro.usuario_id, registro.entidad, registro.entidad_id, registro.ip) == (
        esc.admin_id, "paciente", None, "203.0.113.20")
    assert registro.datos_despues == {"formato": "csv", "filas": 2, "incluir_inactivos": True, "desde": None,
                                      "hasta": None}
    guardado = str(registro.__dict__)
    assert all(dato not in guardado for dato in ("Lucía", "Mateo", "99000001", "99000002", "+54911"))


async def test_los_filtros_de_fecha_y_la_cantidad_de_filas_quedan_en_el_registro_de_turnos(
        session_factory, client: AsyncClient, esc) -> None:  # type: ignore[no-untyped-def]
    for d in (date(2026, 11, 16), date(2026, 11, 17), date(2026, 11, 30)):
        await insertar_turno(session_factory, esc.mundo, local(d, "09:00"))
    await exportar(client, esc.recepcion, entidad="turnos", desde="2026-11-16", hasta="2026-11-20")
    [registro] = await registros(session_factory)
    assert (registro.entidad, registro.datos_despues["filas"], registro.datos_despues["desde"],
            registro.datos_despues["hasta"]) == ("turno", 2, "2026-11-16", "2026-11-20")


async def test_una_exportacion_rechazada_no_deja_registro(session_factory, client: AsyncClient, esc, dos) -> None:  # type: ignore[no-untyped-def]
    assert (await exportar(client, esc.recepcion, entidad="pacientes")).status_code == 403
    assert (await exportar(client, esc.admin, entidad="fichas")).status_code == 422
    assert await registros(session_factory) == []


async def test_si_falla_guardar_el_registro_no_sale_ningun_byte_de_csv(
        session_factory, esc, dos, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    from app.main import app
    from app.plataforma import router_exportacion

    def _falla(*args: object, **kwargs: object) -> None:
        raise RuntimeError("auditoría caída (simulada)")

    monkeypatch.setattr(router_exportacion, "registrar", _falla)
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as c:
        r = await exportar(c, esc.admin, entidad="pacientes")
    assert r.status_code == 500
    assert BOM not in r.content and b"Luc" not in r.content and b"99000001" not in r.content
    assert await registros(session_factory) == []


# --- Descarga interrumpida: el registro ya existe y se liberan la conexión y el lease ----------------------------------

def _scope(token: str, spec_version: str, **query: str) -> dict[str, Any]:
    cadena = "&".join(f"{k}={v}" for k, v in {"formato": "csv", **query}.items())
    return {"type": "http", "asgi": {"version": "3.0", "spec_version": spec_version}, "http_version": "1.1",
            "method": "GET", "scheme": "http", "path": URL, "raw_path": URL.encode(), "root_path": "",
            "query_string": cadena.encode(), "client": ("203.0.113.5", 1234), "server": ("test", 80),
            "headers": [(b"host", b"test"), (b"authorization", f"Bearer {token}".encode())]}


@pytest.mark.parametrize("spec_version", ["2.3", "2.4"])
async def test_una_descarga_cortada_a_la_mitad_deja_el_registro_y_libera_la_conexion_y_el_lease(
        session_factory, esc, limitador, spec_version: str) -> None:  # type: ignore[no-untyped-def]
    from app.main import app
    from app.shared.db import get_engine

    for n in range(1500):  # varios lotes de 500: el corte ocurre con datos todavía por enviar
        await crear_paciente(session_factory, nombre=f"Paciente{n}", apellido="Sintético", dni=f"98{n:06d}",
                             telefono=f"+54911{n:08d}")
    cuerpos = 0
    primero = asyncio.Event()

    async def receive() -> dict[str, Any]:
        await primero.wait()
        return {"type": "http.disconnect"}

    async def send(mensaje: dict[str, Any]) -> None:
        nonlocal cuerpos
        if mensaje["type"] == "http.response.body":
            cuerpos += 1
            primero.set()
            if cuerpos >= 2:
                if spec_version == "2.4":
                    raise OSError("cliente desconectado")
                await asyncio.sleep(0.2)  # le da tiempo al detector de desconexión

    try:
        await app(_scope(esc.admin, spec_version, entidad="pacientes"), receive, send)  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001 - ClientDisconnect u OSError: es el corte que se está simulando
        pass
    [registro] = await registros(session_factory)
    assert registro.datos_despues["filas"] == 1500
    assert get_engine().pool.checkedout() == 0  # type: ignore[attr-defined]
    siguiente = await limitador.consultar(f"rl:v1:export:encurso:{esc.admin_id}", 1)
    assert siguiente.permitido  # el lease se liberó
