"""Helpers de los tests de Google Calendar (C-10). Datos 100 % sintéticos (R19); nunca un token real."""

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Reloj fijo de los ciclos: lunes 16/11/2026 a las 09:00 en la clínica (UTC-3).
AHORA = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)
CLAVE_FERNET = Fernet.generate_key().decode()
Factory = async_sessionmaker[AsyncSession]


def configurar_entorno(monkeypatch: pytest.MonkeyPatch, **extra: str) -> None:
    """Variables GCAL_* sintéticas para el test (Settings se lee del entorno en cada llamada)."""
    base = {"GCAL_CLIENT_ID": "cliente-sintetico.apps.googleusercontent.com", "GCAL_CLIENT_SECRET": "secreto-sintetico",
            "GCAL_TOKEN_CLAVE": CLAVE_FERNET, "PUBLIC_PANEL_URL": "http://localhost:5174",
            "GCAL_REDIRECT_URI": "http://localhost:8000/api/panel/google-calendar/oauth/callback"}
    for clave, valor in {**base, **extra}.items():
        monkeypatch.setenv(clave, valor)


async def sembrar_conexion(factory: Factory, profesional_id: int, *, estado: str = "activa",
                           usuario_id: int | None = None, **campos: Any) -> int:
    """Conexión sintética ya hecha (tokens cifrados con la clave de pruebas)."""
    from app.integraciones.gcal.cifrado import cifrar
    from app.integraciones.gcal.models import GcalConexion

    valores: dict[str, Any] = {"profesional_id": profesional_id, "estado": estado, "usuario_id": usuario_id}
    if estado == "activa":
        valores.update(refresh_token_cifrado=cifrar("refresh-sintetico-001", CLAVE_FERNET),
                       access_token_cifrado=cifrar("token-sintetico-001", CLAVE_FERNET),
                       access_expira_en=datetime.now(timezone.utc) + timedelta(days=3650),
                       cuenta_email="ana.prueba@example.com", conectada_en=AHORA)
    valores.update(campos)
    async with factory() as s:
        conexion = GcalConexion(**valores)
        s.add(conexion)
        await s.flush()
        await s.commit()
        return int(conexion.id)


async def eventos(factory: Factory, conexion_id: int | None = None) -> list[Any]:
    from app.integraciones.gcal.models import EventoCalendar

    async with factory() as s:
        consulta = select(EventoCalendar).order_by(EventoCalendar.id)
        if conexion_id is not None:
            consulta = consulta.where(EventoCalendar.conexion_id == conexion_id)
        return list((await s.execute(consulta)).scalars().all())


async def conflictos(factory: Factory, estado: str | None = None) -> list[Any]:
    from app.integraciones.gcal.models import GcalConflicto

    async with factory() as s:
        consulta = select(GcalConflicto).order_by(GcalConflicto.id)
        if estado is not None:
            consulta = consulta.where(GcalConflicto.estado == estado)
        return list((await s.execute(consulta)).scalars().all())


async def conexion(factory: Factory, conexion_id: int) -> Any:
    from app.integraciones.gcal.models import GcalConexion

    async with factory() as s:
        return (await s.execute(select(GcalConexion).where(GcalConexion.id == conexion_id))).scalar_one()


async def poner_conexion(factory: Factory, conexion_id: int, **campos: Any) -> None:
    from app.integraciones.gcal.models import GcalConexion

    async with factory() as s:
        await s.execute(update(GcalConexion).where(GcalConexion.id == conexion_id).values(**campos))
        await s.commit()


async def ciclo(factory: Factory, proveedor: Any, *, ahora: datetime = AHORA) -> int:
    """Un ciclo completo de ``gcal_sync`` con el proveedor dado."""
    from app.integraciones.gcal.sincronizacion import sincronizar_calendarios

    return await sincronizar_calendarios(factory, proveedor, ahora)


async def sembrar_franja(factory: Factory, conexion_id: int, inicio: datetime, fin: datetime, *,
                         ocupa: bool = True, google_event_id: str | None = None) -> int:
    """Franja ocupada ajena ya guardada (solo horario y ocupación, O19)."""
    from app.integraciones.gcal.models import EventoCalendar

    async with factory() as s:
        franja = EventoCalendar(conexion_id=conexion_id, origen="google", estado="sincronizado", inicio=inicio,
                                fin=fin, ocupa=ocupa,
                                google_event_id=google_event_id or f"franja-sintetica-{os.urandom(4).hex()}")
        s.add(franja)
        await s.flush()
        await s.commit()
        return int(franja.id)
