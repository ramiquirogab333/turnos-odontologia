"""C-06 (8.1): endpoints admin de la seña (acreditar transferencia, configuración). Usuarios sintéticos de C-03."""

from datetime import datetime, timedelta, timezone

import bcrypt
import pytest
from sqlalchemy import select

from app.models.core import RegistroAuditoria, Rol, Usuario, UsuarioRol
from app.pagos.models import ConfiguracionSena
from tests.sena_helpers import (
    configurar_transferencia, fecha_laboral, forzar_vencimiento, iniciar, local, pagos_de, reservar,
    sembrar_agenda, turno_de,
)

CONFIG_VALIDA = {
    "sena_porcentaje": "40.00", "medios_habilitados": ["mercadopago", "transferencia"],
    "texto_politica_reembolso": "Texto sintético de política de reembolso.",
    "expiracion_mp_minutos": 45, "expiracion_transferencia_minutos": 720,
    "transferencia_alias": "clinica.demo.sintetica", "transferencia_cbu": "0000003100000000000043",
    "transferencia_titular": "Clínica Demo Sintética",
}


async def _usuario(factory, client, rol: str) -> tuple[int, dict[str, str]]:
    email, clave = f"{rol}@sena.test", "password-sintetica-123"
    async with factory() as s:
        r = Rol(nombre=rol)
        u = Usuario(email=email, nombre_completo=f"Usuario {rol}",
                    hashed_password=bcrypt.hashpw(clave.encode(), bcrypt.gensalt()).decode())
        s.add_all([r, u])
        await s.flush()
        s.add(UsuarioRol(usuario_id=u.id, rol_id=r.id))
        uid = int(u.id)
        await s.commit()
    login = await client.post("/api/auth/login", json={"email": email, "password": clave})
    assert login.status_code == 200, login.text
    return uid, {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _transferencia_pendiente(client, ids, factory, pasarela_unused=None):
    f = fecha_laboral()
    await sembrar_agenda(factory, ids, f)
    await configurar_transferencia(factory)
    reserva = await reservar(client, ids, local(f, "10:00"))
    r = await iniciar(client, reserva, "transferencia")
    assert r.status_code == 201, r.text
    return reserva, r.json()["pago_id"]


# --- Acreditar transferencia ---------------------------------------------------------------------

async def test_recepcion_acredita_la_transferencia_y_queda_auditado(client, seed_ids, session_factory, pasarela) -> None:
    uid, auth = await _usuario(session_factory, client, "recepcion")
    reserva, pago_id = await _transferencia_pendiente(client, seed_ids, session_factory)
    r = await client.post(f"/api/admin/pagos-sena/{pago_id}/acreditar", headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["estado_pago"] == "acreditado" and r.json()["estado_turno"] == "reservado"
    (pago,) = await pagos_de(session_factory, reserva["turno_id"])
    assert pago.estado == "acreditado" and pago.acreditado_por_usuario_id == uid
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "reservado"
    async with session_factory() as s:
        aud = (await s.execute(select(RegistroAuditoria).where(
            RegistroAuditoria.entidad == "turno", RegistroAuditoria.entidad_id == str(reserva["turno_id"]),
            RegistroAuditoria.datos_despues["origen"].astext == "acreditacion_sena"))).scalar_one()
    assert aud.usuario_id == uid and aud.datos_despues["medio"] == "transferencia"


async def test_odontologo_no_puede_acreditar_y_sin_token_es_401(client, seed_ids, session_factory, pasarela) -> None:
    _, auth = await _usuario(session_factory, client, "odontologo")
    reserva, pago_id = await _transferencia_pendiente(client, seed_ids, session_factory)
    assert (await client.post(f"/api/admin/pagos-sena/{pago_id}/acreditar", headers=auth)).status_code == 403
    assert (await client.post(f"/api/admin/pagos-sena/{pago_id}/acreditar")).status_code == 401
    (pago,) = await pagos_de(session_factory, reserva["turno_id"])
    assert pago.estado == "pendiente"


async def test_pago_de_mercadopago_o_transferencia_vencida_o_inexistente(
        client, seed_ids, session_factory, pasarela) -> None:
    _, auth = await _usuario(session_factory, client, "admin")
    reserva, pago_tr = await _transferencia_pendiente(client, seed_ids, session_factory)
    mp = await iniciar(client, reserva, "mercadopago")  # la transferencia anterior queda vencida
    pago_mp = mp.json()["pago_id"]

    r_mp = await client.post(f"/api/admin/pagos-sena/{pago_mp}/acreditar", headers=auth)
    r_vencida = await client.post(f"/api/admin/pagos-sena/{pago_tr}/acreditar", headers=auth)
    assert (r_mp.status_code, r_mp.json()["motivo"]) == (409, "no_es_transferencia")
    assert (r_vencida.status_code, r_vencida.json()["motivo"]) == (409, "pago_no_pendiente")
    assert (await client.post("/api/admin/pagos-sena/999999/acreditar", headers=auth)).status_code == 404
    estados = [p.estado for p in await pagos_de(session_factory, reserva["turno_id"])]
    assert estados == ["vencido", "pendiente"]
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "en_espera"


async def test_transferencia_pendiente_con_el_plazo_cumplido_es_409_vencida(
        client, seed_ids, session_factory, pasarela) -> None:
    _, auth = await _usuario(session_factory, client, "admin")
    reserva, pago_id = await _transferencia_pendiente(client, seed_ids, session_factory)
    await forzar_vencimiento(session_factory, reserva["turno_id"], datetime.now(timezone.utc) - timedelta(minutes=1))
    r = await client.post(f"/api/admin/pagos-sena/{pago_id}/acreditar", headers=auth)
    assert (r.status_code, r.json()["motivo"]) == (409, "vencido")
    assert (await turno_de(session_factory, reserva["turno_id"])).estado == "en_espera"


# --- Configuración --------------------------------------------------------------------------------

async def test_configuracion_inicial_por_defecto(client, session_factory) -> None:
    _, auth = await _usuario(session_factory, client, "admin")
    r = await client.get("/api/admin/config/sena", headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sena_porcentaje"] == "30.00" and sorted(body["medios_habilitados"]) == ["mercadopago", "transferencia"]
    assert (body["expiracion_mp_minutos"], body["expiracion_transferencia_minutos"]) == (30, 1440)
    assert body["texto_politica_reembolso"].startswith("Si cancelás con 24 h o más")


async def test_admin_actualiza_la_configuracion_y_se_audita(client, session_factory) -> None:
    uid, auth = await _usuario(session_factory, client, "admin")
    r = await client.put("/api/admin/config/sena", json=CONFIG_VALIDA, headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["sena_porcentaje"] == "40.00" and r.json()["expiracion_mp_minutos"] == 45
    assert (await client.get("/api/admin/config/sena", headers=auth)).json()["transferencia_cbu"] == "0000003100000000000043"
    async with session_factory() as s:
        aud = (await s.execute(select(RegistroAuditoria).where(
            RegistroAuditoria.entidad == "configuracion_sena"))).scalar_one()
    assert aud.usuario_id == uid and aud.datos_antes["sena_porcentaje"] == "30.00"
    assert aud.datos_despues["sena_porcentaje"] == "40.00"


@pytest.mark.parametrize("cambio", [
    {"sena_porcentaje": "0"}, {"sena_porcentaje": "100.01"}, {"sena_porcentaje": "-5"},
    {"medios_habilitados": []}, {"medios_habilitados": ["efectivo"]},
    {"medios_habilitados": ["mercadopago", "efectivo"]},
    {"transferencia_cbu": "123"}, {"transferencia_alias": "abc"},
    {"expiracion_mp_minutos": 1}, {"expiracion_transferencia_minutos": 99999},
    {"texto_politica_reembolso": ""}, {"campo_inventado": 1},
])
async def test_configuracion_invalida_es_422_y_no_cambia(client, session_factory, cambio) -> None:
    _, auth = await _usuario(session_factory, client, "admin")
    r = await client.put("/api/admin/config/sena", json={**CONFIG_VALIDA, **cambio}, headers=auth)
    assert r.status_code == 422, r.text
    async with session_factory() as s:
        cfg = (await s.execute(select(ConfiguracionSena))).scalar_one()
    assert str(cfg.sena_porcentaje) == "30.00" and cfg.transferencia_cbu is None


async def test_porcentaje_100_se_acepta(client, session_factory) -> None:
    _, auth = await _usuario(session_factory, client, "admin")
    r = await client.put("/api/admin/config/sena", json={**CONFIG_VALIDA, "sena_porcentaje": "100.00"}, headers=auth)
    assert r.status_code == 200 and r.json()["sena_porcentaje"] == "100.00"


async def test_roles_en_configuracion(client, session_factory) -> None:
    _, odonto = await _usuario(session_factory, client, "odontologo")
    assert (await client.get("/api/admin/config/sena", headers=odonto)).status_code == 403
    assert (await client.put("/api/admin/config/sena", json=CONFIG_VALIDA, headers=odonto)).status_code == 403
    assert (await client.get("/api/admin/config/sena")).status_code == 401
    _, recep = await _usuario(session_factory, client, "recepcion")
    assert (await client.get("/api/admin/config/sena", headers=recep)).status_code == 200
