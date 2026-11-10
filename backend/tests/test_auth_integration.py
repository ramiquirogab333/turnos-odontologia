"""Integración de auth C-03: login, refresh, logout, me, RBAC y acceso público.

Strict TDD: RED (test falla) → GREEN (código mínimo) → TRIANGULATE (2do caso) → REFACTOR.
"""

import bcrypt
import pytest
import jwt
from datetime import datetime, timedelta, timezone
from fastapi import status
from httpx import AsyncClient

from app.models.core import RegistroAuditoria, Rol, Usuario, UsuarioRol
from app.shared.settings import get_settings


# ---------------------------------------------------------------------------
# Helpers de setup
# ---------------------------------------------------------------------------

async def _crear_usuario_con_rol(
    session, email: str, password_plain: str, nombre: str, rol_nombre: str
) -> int:
    """Crea un usuario con rol dado y retorna su id. Hashea con bcrypt directo."""
    hashed = bcrypt.hashpw(password_plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    rol = Rol(nombre=rol_nombre)
    usuario = Usuario(
        email=email,
        nombre_completo=nombre,
        hashed_password=hashed,
    )
    session.add_all([rol, usuario])
    await session.flush()
    session.add(UsuarioRol(usuario_id=usuario.id, rol_id=rol.id))
    await session.flush()
    return int(usuario.id)


async def _login(client: AsyncClient, email: str, password: str):
    """POST /api/auth/login y retorna la respuesta httpx."""
    return await client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )


# ---------------------------------------------------------------------------
# 5.1 Login correcto → 200 con tokens (Happy Path)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_login_correcto_devuelve_200_con_tokens(
    session_factory, clean_db, client
):
    async with session_factory() as session:
        await _crear_usuario_con_rol(
            session, "recepcion@turnos.test", "password123", "Recepcion Test", "recepcion"
        )
        await session.commit()

    resp = await _login(client, "recepcion@turnos.test", "password123")
    assert resp.status_code == status.HTTP_200_OK, resp.text
    body = resp.json()
    assert "access_token" in body
    # C-08 (D10): el refresh viaja solo en la cookie HttpOnly, nunca en el JSON
    assert "refresh_token" not in body
    assert body["token_type"] == "bearer"
    assert "refresh_token" in resp.cookies


@pytest.mark.asyncio
async def test_login_correcto_claims_access_token(
    session_factory, clean_db, client
):
    """Segundo caso (triangulación): access_token decodable con claims requeridos."""
    async with session_factory() as session:
        uid = await _crear_usuario_con_rol(
            session, "odontologo@turnos.test", "password123", "Odontologo Test", "odontologo"
        )
        await session.commit()

    resp = await _login(client, "odontologo@turnos.test", "password123")
    assert resp.status_code == status.HTTP_200_OK
    access_token = resp.json()["access_token"]

    settings = get_settings()
    payload = jwt.decode(
        access_token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "iat"]},
    )
    assert payload["sub"] == str(uid)
    assert payload["email"] == "odontologo@turnos.test"
    assert "odontologo" in payload["roles"]
    assert payload["type"] == "access"
    assert "jti" in payload
    assert "iat" in payload
    assert "exp" in payload


# ---------------------------------------------------------------------------
# 5.2 Credenciales inválidas → 401 (Error de Negocio)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_login_credenciales_invalidas_devuelve_401(
    session_factory, clean_db, client
):
    resp = await _login(client, "noexiste@turnos.test", "cualquiera")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_login_password_incorrecto_devuelve_401(
    session_factory, clean_db, client
):
    """Segundo caso (triangulación): usuario existe pero password mal."""
    async with session_factory() as session:
        await _crear_usuario_con_rol(
            session, "recepcion2@turnos.test", "password123", "Recepcion 2", "recepcion"
        )
        await session.commit()

    resp = await _login(client, "recepcion2@turnos.test", "password_erroneo")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# 5.3 Refresh rotation con blacklist del jti anterior (Caso de Borde)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_refresh_rotation_blacklistea_jti_anterior(
    session_factory, clean_db, client
):
    async with session_factory() as session:
        await _crear_usuario_con_rol(
            session, "admin@turnos.test", "password123", "Admin Test", "admin"
        )
        await session.commit()

    # Login para obtener refresh token
    resp_login = await _login(client, "admin@turnos.test", "password123")
    assert resp_login.status_code == status.HTTP_200_OK
    refresh_token_viejo = resp_login.cookies["refresh_token"]

    # Rotar: POST /api/auth/refresh con la cookie del refresh viejo y la cabecera anti-CSRF (C-08, D10)
    cabeceras = {"Cookie": f"refresh_token={refresh_token_viejo}", "X-Panel-Csrf": "1"}
    resp_refresh = await client.post("/api/auth/refresh", headers=cabeceras)
    assert resp_refresh.status_code == status.HTTP_200_OK, resp_refresh.text
    nuevo_par = resp_refresh.json()
    assert "access_token" in nuevo_par
    assert "refresh_token" not in nuevo_par
    assert "refresh_token" in resp_refresh.cookies

    # El jti viejo ya no debe ser usable para otro refresh
    resp_doble = await client.post("/api/auth/refresh", headers=cabeceras)
    assert resp_doble.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# 5.4 Matriz RBAC por rol (odontólogo vs recepcion-admin)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_require_role_recepcion_permite_crud(
    session_factory, clean_db, client
):
    """recepcion puede acceder a /api/auth/me; odontólogo también (ambos autenticados)."""
    async with session_factory() as session:
        await _crear_usuario_con_rol(
            session, "recepcion@turnos.test", "password123", "Recepcion", "recepcion"
        )
        await _crear_usuario_con_rol(
            session, "odontologo@turnos.test", "password123", "Odontologo", "odontologo"
        )
        await session.commit()

    # Login recepción
    resp_r = await _login(client, "recepcion@turnos.test", "password123")
    assert resp_r.status_code == status.HTTP_200_OK
    token_r = resp_r.json()["access_token"]

    # Login odontólogo
    resp_o = await _login(client, "odontologo@turnos.test", "password123")
    assert resp_o.status_code == status.HTTP_200_OK
    token_o = resp_o.json()["access_token"]

    # recepcion: GET /api/auth/me → 200 con rol recepcion
    resp_me_r = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token_r}"}
    )
    assert resp_me_r.status_code == status.HTTP_200_OK
    assert "recepcion" in resp_me_r.json()["roles"]

    # odontólogo: GET /api/auth/me → 200 con rol odontologo
    resp_me_o = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token_o}"}
    )
    assert resp_me_o.status_code == status.HTTP_200_OK
    assert "odontologo" in resp_me_o.json()["roles"]


# ---------------------------------------------------------------------------
# 5.5 Token expirado → 401 (Error de negocio en decode)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_token_expirado_rechazado_401(
    session_factory, clean_db, client
):
    """Usar un access token con exp en el pasado → 401 en endpoint protegido."""
    settings = get_settings()
    token_expirado = jwt.encode(
        {
            "sub": "999",
            "roles": ["recepcion"],
            "email": "expired@turnos.test",
            "jti": "jti-expirado-sintetico",
            "type": "access",
            "iat": datetime.now(timezone.utc) - timedelta(hours=2),
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    resp = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token_expirado}"}
    )
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# 5.6 Login/logout auditados en RegistroAuditoria (RN-GL-01)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_login_y_logout_auditados_en_registro_auditoria(
    session_factory, clean_db, client
):
    async with session_factory() as session:
        uid = await _crear_usuario_con_rol(
            session, "auditado@turnos.test", "password123", "Auditado", "recepcion"
        )
        await session.commit()

    resp_login = await _login(client, "auditado@turnos.test", "password123")
    assert resp_login.status_code == status.HTTP_200_OK
    access_token = resp_login.json()["access_token"]

    resp_logout = await client.post(
        "/api/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp_logout.status_code == status.HTTP_200_OK

    # Verificar registros de auditoría
    async with session_factory() as session:
        from sqlalchemy import select

        result = await session.execute(
            select(RegistroAuditoria).where(
                RegistroAuditoria.usuario_id == uid,
                RegistroAuditoria.accion.in_(["LOGIN_OK", "LOGOUT"]),
            )
        )
        registros = result.scalars().all()
        assert len(registros) >= 2
        acciones = {r.accion for r in registros}
        assert "LOGIN_OK" in acciones
        assert "LOGOUT" in acciones


# ---------------------------------------------------------------------------
# C-11 (9.8): matriz RBAC del panel con la odontóloga redefinida (O2-O4, O15, O16)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rbac_la_odontologa_marca_atendido_y_edita_la_ficha_de_su_paciente(session_factory, client, reloj):
    from datetime import timedelta

    from tests.clinica_helpers import AHORA, crear_paciente, hace, sembrar_escenario, turno_de
    from tests.conftest import bearer

    reloj(AHORA)
    esc = await sembrar_escenario(session_factory)
    lucia = await crear_paciente(session_factory)
    await turno_de(session_factory, esc, lucia, hace(dias=60))  # atendida hace dos meses
    propio = await turno_de(session_factory, esc, None, AHORA + timedelta(hours=1), "reservado")
    cab = bearer(esc.ana)
    assert (await client.post(f"/api/panel/turnos/{propio}/atendido", headers=cab)).status_code == status.HTTP_200_OK
    ficha = {"alergias": "", "medicacion": "", "antecedentes_medicos": "", "observaciones": "", "version": 0}
    assert (await client.put(f"/api/panel/pacientes/{lucia}/ficha", json=ficha, headers=cab)).status_code == 200


@pytest.mark.asyncio
async def test_rbac_la_odontologa_no_cancela_ni_crea_presupuestos_ni_registra_pagos(session_factory, client, reloj):
    from datetime import timedelta

    from tests.clinica_helpers import AHORA, crear_paciente, hace, sembrar_escenario, turno_de
    from tests.conftest import bearer
    from tests.presupuestos_helpers import aceptado, sembrar_catalogo

    reloj(AHORA)
    esc = await sembrar_escenario(session_factory)
    cat = await sembrar_catalogo(session_factory)
    lucia = await crear_paciente(session_factory, obra_social_id=cat["swiss"])
    await turno_de(session_factory, esc, lucia, hace(dias=60))
    futuro = await turno_de(session_factory, esc, lucia, AHORA + timedelta(days=5), "confirmado")
    pid = await aceptado(client, esc.recepcion, lucia, (cat["limpieza"], 1))
    cab = bearer(esc.ana)
    assert (await client.post(f"/api/panel/turnos/{futuro}/cancelar", headers=cab)).status_code == 403
    assert (await client.post(f"/api/panel/pacientes/{lucia}/presupuestos", headers=cab,
                              json={"lineas": [{"tratamiento_id": cat["limpieza"], "cantidad": 1}]})).status_code == 403
    assert (await client.post(f"/api/panel/pacientes/{lucia}/presupuestos/{pid}/pagos", headers=cab,
                              json={"medio": "transferencia", "monto": "100.00"})).status_code == 403


@pytest.mark.asyncio
async def test_rbac_recepcion_crea_pacientes_y_la_odontologa_no_edita_pacientes_ajenos(session_factory, client, reloj):
    from tests.clinica_helpers import AHORA, crear_paciente, sembrar_escenario
    from tests.conftest import bearer

    reloj(AHORA)
    esc = await sembrar_escenario(session_factory)
    alta = {"nombre": "Lucía", "apellido": "Ejemplo", "dni": "99000001", "telefono": "+5491100000001"}
    creado = await client.post("/api/panel/pacientes", json=alta, headers=bearer(esc.recepcion))
    assert creado.status_code == status.HTTP_201_CREATED
    ajeno = await crear_paciente(session_factory, dni="99000002")
    editar = await client.put(f"/api/panel/pacientes/{ajeno}", json={**alta, "dni": "99000002"}, headers=bearer(esc.ana))
    assert editar.status_code == status.HTTP_403_FORBIDDEN
