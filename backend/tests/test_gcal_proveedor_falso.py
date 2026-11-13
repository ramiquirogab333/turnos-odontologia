"""C-10 (4.1): contrato del puerto ``ProveedorCalendario`` sobre el proveedor falso en memoria. Sintético (R19)."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.integraciones.gcal.contenido import armar_contenido
from app.integraciones.gcal.proveedor import (AccesoRevocado, ErrorTransitorio, EtagDesactualizado, EventoDuplicado,
                                              EventoInexistente, SyncTokenVencido)
from app.integraciones.gcal.proveedor_falso import ProveedorFalso

BA = ZoneInfo("America/Argentina/Buenos_Aires")
INICIO = datetime(2031, 11, 17, 13, 0, tzinfo=timezone.utc)
CAL = "primary"
ACCESO = "token-sintetico-001"


def _contenido(titulo_tratamiento: str = "Limpieza", inicio: datetime = INICIO):
    return armar_contenido(turno_id=1, tratamiento=titulo_tratamiento, sillon="Sillón 1", inicio=inicio,
                           fin=inicio + timedelta(minutes=30), zona=BA, url_panel="http://panel")


async def test_insertar_con_id_propio_y_el_segundo_intento_es_duplicado() -> None:
    proveedor = ProveedorFalso()
    creado = await proveedor.insertar(ACCESO, CAL, "evento-0001", _contenido())
    assert creado.id == "evento-0001" and creado.etag and creado.propias["turnos_sistema"] == "1"
    with pytest.raises(EventoDuplicado):
        await proveedor.insertar(ACCESO, CAL, "evento-0001", _contenido())


async def test_actualizar_con_etag_vigente_cambia_el_horario_y_con_uno_viejo_falla() -> None:
    proveedor = ProveedorFalso()
    creado = await proveedor.insertar(ACCESO, CAL, "evento-0001", _contenido())
    nuevo = await proveedor.actualizar(ACCESO, CAL, "evento-0001", _contenido(inicio=INICIO + timedelta(hours=3)),
                                       creado.etag or "")
    assert nuevo.inicio == INICIO + timedelta(hours=3) and nuevo.etag != creado.etag
    with pytest.raises(EtagDesactualizado):
        await proveedor.actualizar(ACCESO, CAL, "evento-0001", _contenido(), creado.etag or "")


async def test_borrar_y_borrar_de_nuevo() -> None:
    proveedor = ProveedorFalso()
    await proveedor.insertar(ACCESO, CAL, "evento-0001", _contenido())
    await proveedor.borrar(ACCESO, CAL, "evento-0001")
    assert (await proveedor.obtener(ACCESO, CAL, "evento-0001")).estado == "cancelled"  # type: ignore[union-attr]
    with pytest.raises(EventoInexistente):
        await proveedor.borrar(ACCESO, CAL, "evento-0001")
    with pytest.raises(EventoInexistente):
        await proveedor.borrar(ACCESO, CAL, "nunca-existio")
    with pytest.raises(EventoDuplicado):  # Google no reutiliza el id de un evento borrado
        await proveedor.insertar(ACCESO, CAL, "evento-0001", _contenido())


async def test_listar_incremental_trae_solo_los_cambios_y_los_borrados_como_cancelados() -> None:
    proveedor = ProveedorFalso()
    ajeno = proveedor.crear_ocupado(INICIO, INICIO + timedelta(hours=1))
    primero = await proveedor.listar(ACCESO, CAL, None, INICIO - timedelta(days=1), INICIO + timedelta(days=30))
    assert [e.id for e in primero.eventos] == [ajeno] and primero.sync_token
    vacio = await proveedor.listar(ACCESO, CAL, primero.sync_token, None, None)
    assert vacio.eventos == [] and vacio.sync_token
    proveedor.borrar_externo(ajeno)
    cambio = await proveedor.listar(ACCESO, CAL, vacio.sync_token, None, None)
    assert [(e.id, e.estado) for e in cambio.eventos] == [(ajeno, "cancelled")]


async def test_un_sync_token_invalidado_da_410() -> None:
    proveedor = ProveedorFalso()
    primero = await proveedor.listar(ACCESO, CAL, None, INICIO, INICIO + timedelta(days=1))
    proveedor.invalidar_sync_tokens()
    with pytest.raises(SyncTokenVencido):
        await proveedor.listar(ACCESO, CAL, primero.sync_token, None, None)


async def test_renovar_token_y_acceso_revocado() -> None:
    proveedor = ProveedorFalso()
    tokens = await proveedor.renovar_token("refresh-sintetico-001")
    assert tokens.access_token and tokens.expira_en > datetime.now(timezone.utc)
    proveedor.revocar_acceso()
    with pytest.raises(AccesoRevocado):
        await proveedor.renovar_token("refresh-sintetico-001")


async def test_las_fallas_inyectadas_son_transitorias_y_se_consumen() -> None:
    proveedor = ProveedorFalso()
    proveedor.fallar(ErrorTransitorio(503), veces=2)
    for _ in range(2):
        with pytest.raises(ErrorTransitorio):
            await proveedor.insertar(ACCESO, CAL, "evento-0001", _contenido())
    assert (await proveedor.insertar(ACCESO, CAL, "evento-0001", _contenido())).id == "evento-0001"
    assert proveedor.llamadas.count("insertar") == 3
