"""C-14 (4.1, 4.3; D2; O2, O3): consulta de impacto y turnos intactos ante cambios del catálogo.

Datos 100 % sintéticos (R19). El reloj va inyectado (R4) y la clínica trabaja en ``America/Argentina/Buenos_Aires`` mientras
el servidor corre en UTC. Requiere PostgreSQL en localhost:5433.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.core import RegistroAuditoria
from app.pagos.models import PagoSena
from app.turnos.models import Turno
from tests.conftest import bearer, crear_usuario_panel
from tests.panel_helpers import BA, LUNES, insertar_pago, insertar_turno, local, sembrar_mundo, turno

Factory = async_sessionmaker[AsyncSession]

# Sábado 15/11/2031 12:00 en Buenos Aires: todos los turnos de la semana siguiente son futuros.
AHORA = datetime(2031, 11, 15, 12, 0, tzinfo=BA)


async def _impacto(client: AsyncClient, recurso: str, id_: int, token: str | None = None):
    cabeceras = {} if token is None else bearer(token)
    return await client.get(f"/api/admin/{recurso}/{id_}/impacto", headers=cabeceras)


async def _franja_de(client: AsyncClient, profesional_id: int, dia: int) -> int:
    franjas = (await client.get("/api/admin/disponibilidad")).json()
    return next(f["id"] for f in franjas if f["profesional_id"] == profesional_id and f["dia_semana"] == dia)


# --- 4.1 Impacto ------------------------------------------------------------------------------------------------------

async def test_el_impacto_de_una_franja_cuenta_solo_los_turnos_vigentes_dentro_del_horario_sin_datos_de_pacientes(
        client_recepcion: AsyncClient, session_factory: Factory, reloj) -> None:
    reloj(AHORA)
    mundo = await sembrar_mundo(session_factory, franja=("14:00", "18:00"))
    await insertar_turno(session_factory, mundo, local(LUNES, "14:30"), estado="reservado")
    await insertar_turno(session_factory, mundo, local(LUNES, "17:30"), estado="en_espera", sillon="s2")
    await insertar_turno(session_factory, mundo, local(LUNES, "18:00"), estado="reservado")  # empieza justo al cerrar
    franja = await _franja_de(client_recepcion, mundo["ana"], 0)
    r = await _impacto(client_recepcion, "disponibilidad", franja)
    assert r.status_code == 200, r.text
    assert r.json() == {"turnos_futuros": 2, "primero": local(LUNES, "14:30").isoformat()}
    texto = r.text.lower()
    assert "carlos" not in texto and "telefono" not in texto and "+54" not in texto


async def test_el_impacto_de_una_franja_no_cuenta_otro_dia_ni_otro_profesional(
        client_recepcion: AsyncClient, session_factory: Factory, reloj) -> None:
    reloj(AHORA)
    mundo = await sembrar_mundo(session_factory, franja=("09:00", "13:00"))
    await insertar_turno(session_factory, mundo, local(LUNES + timedelta(days=1), "09:30"))  # martes
    await insertar_turno(session_factory, mundo, local(LUNES, "09:30"), prof="bruno", sillon="s2")
    franja = await _franja_de(client_recepcion, mundo["ana"], 0)
    r = await _impacto(client_recepcion, "disponibilidad", franja)
    assert r.json() == {"turnos_futuros": 0, "primero": None}


async def test_un_turno_de_las_23_30_locales_del_lunes_cuenta_como_lunes_aunque_en_utc_sea_martes(
        client_recepcion: AsyncClient, session_factory: Factory, reloj) -> None:
    reloj(AHORA)
    mundo = await sembrar_mundo(session_factory, franja=("23:00", "23:59"))
    tarde = local(LUNES, "23:30")
    assert tarde.astimezone(timezone.utc).weekday() == 1  # en UTC ya es martes
    await insertar_turno(session_factory, mundo, tarde)
    lunes = await _franja_de(client_recepcion, mundo["ana"], 0)
    martes = await _franja_de(client_recepcion, mundo["ana"], 1)
    assert (await _impacto(client_recepcion, "disponibilidad", lunes)).json()["turnos_futuros"] == 1
    assert (await _impacto(client_recepcion, "disponibilidad", martes)).json()["turnos_futuros"] == 0


async def test_el_impacto_de_un_tratamiento_profesional_y_sillon_cuenta_por_fk_los_turnos_vigentes(
        client_recepcion: AsyncClient, session_factory: Factory, reloj) -> None:
    reloj(AHORA)
    mundo = await sembrar_mundo(session_factory)
    await insertar_turno(session_factory, mundo, local(LUNES, "09:00"), estado="confirmado")
    await insertar_turno(session_factory, mundo, local(LUNES, "10:00"), estado="reservado", sillon="s2")
    await insertar_turno(session_factory, mundo, local(LUNES, "11:00"), estado="cancelado")
    assert (await _impacto(client_recepcion, "tratamientos", mundo["trat"])).json()["turnos_futuros"] == 2
    assert (await _impacto(client_recepcion, "profesionales", mundo["ana"])).json()["turnos_futuros"] == 2
    assert (await _impacto(client_recepcion, "profesionales", mundo["bruno"])).json() == {"turnos_futuros": 0, "primero": None}
    assert (await _impacto(client_recepcion, "sillones", mundo["s1"])).json()["turnos_futuros"] == 1
    assert (await _impacto(client_recepcion, "sillones", mundo["s2"])).json()["turnos_futuros"] == 1


async def test_turnos_pasados_cancelados_o_ausentes_no_cuentan_y_el_primero_es_nulo(
        client_recepcion: AsyncClient, session_factory: Factory, reloj) -> None:
    reloj(AHORA)
    mundo = await sembrar_mundo(session_factory)
    await insertar_turno(session_factory, mundo, AHORA - timedelta(days=1), estado="atendido")
    await insertar_turno(session_factory, mundo, local(LUNES, "09:00"), estado="cancelado", sillon="s2")
    await insertar_turno(session_factory, mundo, local(LUNES, "10:00"), estado="ausente")
    r = await _impacto(client_recepcion, "tratamientos", mundo["trat"])
    assert r.status_code == 200 and r.json() == {"turnos_futuros": 0, "primero": None}


async def test_un_turno_que_ya_empezo_no_cuenta_como_futuro(client_recepcion: AsyncClient, session_factory: Factory, reloj) -> None:
    mundo = await sembrar_mundo(session_factory)
    inicio = local(LUNES, "09:00")
    await insertar_turno(session_factory, mundo, inicio)
    reloj(inicio)  # justo ahora: ``inicio > ahora`` es falso
    assert (await _impacto(client_recepcion, "tratamientos", mundo["trat"])).json()["turnos_futuros"] == 0
    reloj(inicio - timedelta(minutes=1))
    assert (await _impacto(client_recepcion, "tratamientos", mundo["trat"])).json()["turnos_futuros"] == 1


async def test_la_odontologa_recibe_403_y_un_id_inexistente_404(
        client_recepcion: AsyncClient, session_factory: Factory, reloj) -> None:
    reloj(AHORA)
    mundo = await sembrar_mundo(session_factory)
    _, token = await crear_usuario_panel(session_factory, "dra.ficticia@turnos.test", ["odontologo"],
                                         profesional_id=mundo["ana"])
    assert (await _impacto(client_recepcion, "tratamientos", mundo["trat"], token)).status_code == 403
    for recurso in ("tratamientos", "profesionales", "sillones", "disponibilidad"):
        assert (await _impacto(client_recepcion, recurso, 999999)).status_code == 404, recurso


async def test_la_consulta_de_impacto_no_audita_nada(client_recepcion: AsyncClient, session_factory: Factory, reloj) -> None:
    reloj(AHORA)
    mundo = await sembrar_mundo(session_factory)
    await _impacto(client_recepcion, "tratamientos", mundo["trat"])
    async with session_factory() as s:
        assert list((await s.execute(select(RegistroAuditoria))).scalars()) == []


# --- 4.3 Los cambios del catálogo no alteran turnos existentes ---------------------------------------------------------

async def test_alargar_un_tratamiento_y_subir_su_precio_no_toca_el_turno_tomado_ni_su_sena_y_los_horarios_nuevos_duran_lo_nuevo(
        client_recepcion: AsyncClient, session_factory: Factory) -> None:
    mundo = await sembrar_mundo(session_factory, franja=("09:00", "13:00"), duracion=45)
    id_turno = await insertar_turno(session_factory, mundo, local(LUNES, "10:00"), minutos=45)
    pago = await insertar_pago(session_factory, id_turno, "acreditado", monto="7500.00")
    antes = await turno(session_factory, id_turno)
    r = await client_recepcion.put(f"/api/admin/tratamientos/{mundo['trat']}",
                                   json={"duracion_minutos": 60, "precio_base": "30000.00"})
    assert r.status_code == 200, r.text
    despues = await turno(session_factory, id_turno)
    assert (despues.inicio, despues.fin, despues.estado, despues.sillon_id) == (antes.inicio, antes.fin, antes.estado, antes.sillon_id)
    assert despues.fin - despues.inicio == timedelta(minutes=45)
    async with session_factory() as s:
        monto = (await s.execute(select(PagoSena.monto).where(PagoSena.id == pago))).scalar_one()
    assert monto == Decimal("7500.00")
    horarios = (await client_recepcion.get("/api/public/disponibilidad", params={
        "profesional_id": mundo["bruno"], "tratamiento_id": mundo["trat"],
        "desde": LUNES.isoformat(), "hasta": LUNES.isoformat()})).json()["slots"]
    assert horarios and all(
        datetime.fromisoformat(h["fin"]) - datetime.fromisoformat(h["inicio"]) == timedelta(minutes=60) for h in horarios)


async def test_desactivar_un_profesional_con_turnos_confirmados_no_los_cancela_ni_publica_eventos(
        client_recepcion: AsyncClient, session_factory: Factory, notificador) -> None:
    mundo = await sembrar_mundo(session_factory)
    ids = [await insertar_turno(session_factory, mundo, local(LUNES, hhmm), estado="confirmado") for hhmm in ("09:00", "10:00")]
    r = await client_recepcion.put(f"/api/admin/profesionales/{mundo['ana']}", json={"activo": False})
    assert r.status_code == 200, r.text
    async with session_factory() as s:
        turnos = list((await s.execute(select(Turno).where(Turno.id.in_(ids)))).scalars())
    assert [t.estado for t in turnos] == ["confirmado", "confirmado"]
    assert notificador.eventos == []  # ningún aviso ni evento nuevo


async def test_al_pausar_una_franja_el_turno_tomado_sigue_y_al_reprogramarlo_despues_del_cambio_dura_lo_vigente(
        client_recepcion: AsyncClient, session_factory: Factory, reloj, notificador) -> None:
    reloj(AHORA)
    mundo = await sembrar_mundo(session_factory, franja=("09:00", "13:00"), duracion=45)
    id_turno = await insertar_turno(session_factory, mundo, local(LUNES, "09:00"), minutos=45)
    codigo = (await turno(session_factory, id_turno)).codigo_gestion
    franja = await _franja_de(client_recepcion, mundo["ana"], 0)
    assert (await client_recepcion.put(f"/api/admin/disponibilidad/{franja}", json={"activo": False})).status_code == 200
    assert (await turno(session_factory, id_turno)).estado == "reservado"  # pausar no toca el turno
    assert (await client_recepcion.put(f"/api/admin/disponibilidad/{franja}", json={"activo": True})).status_code == 200
    assert (await client_recepcion.put(f"/api/admin/tratamientos/{mundo['trat']}", json={"duracion_minutos": 60})).status_code == 200
    sin_cambio = await turno(session_factory, id_turno)
    assert sin_cambio.fin - sin_cambio.inicio == timedelta(minutes=45)  # el turno tomado conserva su duración
    r = await client_recepcion.post("/api/public/gestion/reprogramar", json={"inicio": local(LUNES, "11:00").isoformat()},
                                    headers={"X-Codigo-Gestion": str(codigo)})
    assert r.status_code == 200, r.text
    nuevo = await turno(session_factory, id_turno)
    assert nuevo.fin - nuevo.inicio == timedelta(minutes=60)  # reprogramado después del cambio: duración vigente
