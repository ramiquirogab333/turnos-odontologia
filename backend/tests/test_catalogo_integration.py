"""Integración C-04: CRUD admin del catálogo protegido por RBAC (R15/R13/R16).

Strict TDD: RED (test falla) → GREEN (código mínimo) → TRIANGULATE (2do caso)
→ REFACTOR.

Cubre:
- 6.1 CRUD denegado por rol sin permiso (403) — odontólogo no puede escribir.
- 6.2 duración inválida → 422 (CHECK / validador de borde).
- 6.3 CRUD exitoso con rol recepción (201/200/204) — tratamientos,
  profesionales, sillones, disponibilidad.
- 6.4 auditoría en RegistroAuditoria (RN-GL-01) y recálculo de duración
  (interfaz documentada para C-05).

Requiere PostgreSQL en localhost:5433 (TEST_DATABASE_URL).
"""

import bcrypt
from datetime import time
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.core import RegistroAuditoria, Rol, Usuario, UsuarioRol
from app.turnos.models import Tratamiento


# ---------------------------------------------------------------------------
# Helpers de setup
# ---------------------------------------------------------------------------

async def _crear_usuario_con_rol(session, email: str, password: str, nombre: str, rol_nombre: str) -> int:
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    rol = Rol(nombre=rol_nombre)
    usuario = Usuario(email=email, nombre_completo=nombre, hashed_password=hashed)
    session.add_all([rol, usuario])
    await session.flush()
    session.add(UsuarioRol(usuario_id=usuario.id, rol_id=rol.id))
    await session.flush()
    return int(usuario.id)


async def _login(client: AsyncClient, email: str, password: str):
    return await client.post("/api/auth/login", json={"email": email, "password": password})


async def _token_recepcion(session_factory, client) -> str:
    async with session_factory() as session:
        await _crear_usuario_con_rol(session, "recepcion@turnos.test", "password123", "Recepcion", "recepcion")
        await session.commit()
    resp = await _login(client, "recepcion@turnos.test", "password123")
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


async def _token_odontologo(session_factory, client) -> str:
    async with session_factory() as session:
        await _crear_usuario_con_rol(session, "odontologo@turnos.test", "password123", "Odontologo", "odontologo")
        await session.commit()
    resp = await _login(client, "odontologo@turnos.test", "password123")
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


# ===========================================================================
# 6.1 CRUD denegado por rol sin permiso (403)
# ===========================================================================

@pytest.mark.asyncio
async def test_odontologo_no_puede_crear_tratamiento_403(
    session_factory, clean_db, client
):
    token = await _token_odontologo(session_factory, client)
    r = await client.post(
        "/api/admin/tratamientos",
        json={"nombre": "Limpieza", "duracion_minutos": 30, "precio_base": "5000.00"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_odontologo_no_puede_eliminar_profesional_403(
    session_factory, clean_db, client
):
    token = await _token_odontologo(session_factory, client)
    r = await client.delete(
        "/api/admin/profesionales/1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403, r.text


# ===========================================================================
# 6.2 duración inválida → 422
# ===========================================================================

@pytest.mark.asyncio
async def test_duracion_cero_devuelve_422(session_factory, clean_db, client):
    token = await _token_recepcion(session_factory, client)
    r = await client.post(
        "/api/admin/tratamientos",
        json={"nombre": "Limpieza", "duracion_minutos": 0, "precio_base": "5000.00"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_duracion_negativa_devuelve_422(session_factory, clean_db, client):
    """Segundo caso (triangulación): duracion_minutos < 0 también se rechaza."""
    token = await _token_recepcion(session_factory, client)
    r = await client.post(
        "/api/admin/tratamientos",
        json={"nombre": "Limpieza", "duracion_minutos": -5, "precio_base": "5000.00"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422, r.text


# ===========================================================================
# 6.3 CRUD exitoso con rol recepción (201/200/204)
# ===========================================================================

@pytest.mark.asyncio
async def test_tratamiento_crud_exitoso_recepcion(session_factory, clean_db, client):
    token = await _token_recepcion(session_factory, client)

    # CREATE → 201
    r = await client.post(
        "/api/admin/tratamientos",
        json={"nombre": "Limpieza Dental", "duracion_minutos": 30, "precio_base": "5000.00"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    cuerpo = r.json()
    tratamiento_id = cuerpo["id"]
    assert cuerpo["nombre"] == "Limpieza Dental"
    assert cuerpo["duracion_minutos"] == 30
    assert cuerpo["precio_base"] == "5000.00"

    # GET por id → 200
    r = await client.get(
        f"/api/admin/tratamientos/{tratamiento_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["id"] == tratamiento_id

    # GET list → contiene el tratamiento
    r = await client.get(
        "/api/admin/tratamientos",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert any(t["id"] == tratamiento_id for t in r.json())

    # UPDATE duración → 200 (interfaz de recálculo para C-05)
    r = await client.put(
        f"/api/admin/tratamientos/{tratamiento_id}",
        json={"duracion_minutos": 45},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["duracion_minutos"] == 45

    # DELETE → 204
    r = await client.delete(
        f"/api/admin/tratamientos/{tratamiento_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 204, r.text


@pytest.mark.asyncio
async def test_profesional_crud_exitoso_recepcion(session_factory, clean_db, client):
    token = await _token_recepcion(session_factory, client)

    r = await client.post(
        "/api/admin/profesionales",
        json={"nombre": "Dra. Test", "matricula": "MAT-001", "especialidad": "General"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    r = await client.get(
        f"/api/admin/profesionales/{pid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["matricula"] == "MAT-001"

    r = await client.put(
        f"/api/admin/profesionales/{pid}",
        json={"especialidad": "Ortodoncia"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["especialidad"] == "Ortodoncia"

    r = await client.delete(
        f"/api/admin/profesionales/{pid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_sillon_crud_exitoso_recepcion(session_factory, clean_db, client):
    token = await _token_recepcion(session_factory, client)

    r = await client.post(
        "/api/admin/sillones",
        json={"nombre": "Sillon 1", "estado": "activo"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    sid = r.json()["id"]

    r = await client.put(
        f"/api/admin/sillones/{sid}",
        json={"estado": "mantenimiento"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["estado"] == "mantenimiento"

    r = await client.delete(
        f"/api/admin/sillones/{sid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_disponibilidad_crud_exitoso_recepcion(session_factory, clean_db, client):
    token = await _token_recepcion(session_factory, client)

    # Necesitamos un profesional y (opcional) un sillon como FK padres.
    async with session_factory() as session:
        from app.turnos.models import Profesional, Sillon
        prof = Profesional(nombre="Dr. Dispo", matricula="M-DISPO", especialidad="General")
        sill = Sillon(nombre="S-Dispo", estado="activo")
        session.add_all([prof, sill])
        await session.flush()
        await session.commit()
        prof_id = int(prof.id)
        sill_id = int(sill.id)

    r = await client.post(
        "/api/admin/disponibilidad",
        json={
            "profesional_id": prof_id,
            "dia_semana": 1,
            "hora_inicio": "09:00",
            "hora_fin": "17:00",
            "sillon_defecto_id": sill_id,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    did = r.json()["id"]
    assert r.json()["dia_semana"] == 1
    assert r.json()["hora_inicio"] == "09:00:00"
    assert r.json()["hora_fin"] == "17:00:00"

    r = await client.delete(
        f"/api/admin/disponibilidad/{did}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 204


# ===========================================================================
# 6.4 auditoría en RegistroAuditoria (RN-GL-01)
# ===========================================================================

@pytest.mark.asyncio
async def test_crear_tratamiento_audita_registro_auditoria(session_factory, clean_db, client):
    token = await _token_recepcion(session_factory, client)

    r = await client.post(
        "/api/admin/tratamientos",
        json={"nombre": "Auditado", "duracion_minutos": 30, "precio_base": "1000.00"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    tratamiento_id = r.json()["id"]

    async with session_factory() as session:
        result = await session.execute(
            select(RegistroAuditoria).where(
                RegistroAuditoria.entidad == "tratamiento",
                RegistroAuditoria.accion == "CREATE",
                RegistroAuditoria.entidad_id == str(tratamiento_id),
            )
        )
        registros = result.scalars().all()
    assert len(registros) >= 1
    assert registros[0].datos_despues is not None
    # C-13 (D2): la auditoría no guarda el nombre (identidad del personal): el campo queda en ``campos``.
    assert "nombre" not in registros[0].datos_despues and "nombre" in registros[0].datos_despues["campos"]
    assert registros[0].datos_despues["duracion_minutos"] == 30


@pytest.mark.asyncio
async def test_actualizar_tratamiento_audita_antes_despues(session_factory, clean_db, client):
    """Triangulación: UPDATE registra datos_antes y datos_despues."""
    token = await _token_recepcion(session_factory, client)

    r = await client.post(
        "/api/admin/tratamientos",
        json={"nombre": "Antes", "duracion_minutos": 30, "precio_base": "1000.00"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201
    tratamiento_id = r.json()["id"]

    r = await client.put(
        f"/api/admin/tratamientos/{tratamiento_id}",
        json={"duracion_minutos": 60},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200

    async with session_factory() as session:
        result = await session.execute(
            select(RegistroAuditoria).where(
                RegistroAuditoria.entidad == "tratamiento",
                RegistroAuditoria.accion == "UPDATE",
                RegistroAuditoria.entidad_id == str(tratamiento_id),
            )
        )
        registros = result.scalars().all()
    assert len(registros) >= 1
    assert registros[0].datos_antes["duracion_minutos"] == 30
    assert registros[0].datos_despues["duracion_minutos"] == 60


@pytest.mark.asyncio
async def test_eliminar_tratamiento_audita_delete(session_factory, clean_db, client):
    token = await _token_recepcion(session_factory, client)

    r = await client.post(
        "/api/admin/tratamientos",
        json={"nombre": "Borrable", "duracion_minutos": 30, "precio_base": "1000.00"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201
    tratamiento_id = r.json()["id"]

    r = await client.delete(
        f"/api/admin/tratamientos/{tratamiento_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 204

    async with session_factory() as session:
        result = await session.execute(
            select(RegistroAuditoria).where(
                RegistroAuditoria.entidad == "tratamiento",
                RegistroAuditoria.accion == "DELETE",
                RegistroAuditoria.entidad_id == str(tratamiento_id),
            )
        )
        registros = result.scalars().all()
    assert len(registros) >= 1
    assert registros[0].datos_antes is not None
    assert registros[0].datos_despues is None
