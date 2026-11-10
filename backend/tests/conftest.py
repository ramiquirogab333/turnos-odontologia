"""Shared fixtures: real PostgreSQL + HTTP client (FK parents via ORM harness, C-04 owns CRUDs)."""

import os
import sys
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

# JWT settings son requeridos por Settings (R17: solo env vars). Valores sintéticos
# solo para el entorno de test; en producción deben venir del entorno real.
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-c-03-synthetic-do-not-use-prod")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_MINUTES", "10080")
# C-06: pasarela falsa (sin red), secreto de webhook sintético y barrido desactivado en tests.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("MP_GATEWAY", "fake")
# Asignación forzada (no setdefault): los tests firman con SECRETO_WEBHOOK (tests/sena_helpers.py) y el
# entorno externo (p. ej. CI) no debe poder pisarlo.
os.environ["MP_WEBHOOK_SECRET"] = "secreto-webhook-sintetico-tests"
os.environ.setdefault("SENA_BARRIDO_HABILITADO", "false")

# El código vive en src/ (layout canónico de la cátedra): exponerlo en sys.path
# para que `from app...` resuelva sin instalar el paquete. Vía estándar mínima
# (alternativa: `pythonpath = src` en pytest.ini; se eligió conftest para que
# también funcione al importar los tests fuera de pytest).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
import pytest_asyncio

from httpx import ASGITransport, AsyncClient
from decimal import Decimal

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.auth import TokenBlacklist
from app.models.core import RegistroAuditoria, Usuario, UsuarioRol, Rol
from app.turnos.models import Profesional, Sillon, Tratamiento, Turno

if TYPE_CHECKING:
    from tests.sena_helpers import PasarelaEspia

POLITICA_REEMBOLSO_DEFECTO = (
    "Si cancelás con 24 h o más de anticipación, te devolvemos la seña. "
    "Si no asistís, la seña no se devuelve."
)
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql+asyncpg://turnos:turnos@localhost:5433/turnos"
)


@pytest_asyncio.fixture(autouse=True)
async def _reset_app_engine() -> AsyncIterator[None]:
    """Drop the app's cached engine so it is rebuilt on the current test loop.

    pytest-asyncio uses a fresh event loop per test while ``app.shared.db``
    caches one global engine; reusing it across loops corrupts asyncpg
    connections ("another operation is in progress").
    """
    from app.shared import db as app_db

    old = app_db._engine
    app_db._engine = None
    app_db._session_factory = None
    if old is not None:
        try:
            await old.dispose()
        except Exception:  # noqa: BLE001 - connections belonged to a dead loop
            pass
    try:
        yield
    finally:
        current = app_db._engine
        app_db._engine = None
        app_db._session_factory = None
        if current is not None:
            try:
                await current.dispose()
            except Exception:  # noqa: BLE001
                pass


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Engine + factory bound to the test database."""
    engine = create_async_engine(TEST_DATABASE_URL, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def clean_db(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[None]:
    """Delete all rows before each test via ORM (child first, R14; fixture harness)."""
    from app.clinica.models import OdontogramaRegistro, PagoPresupuesto, Presupuesto, PresupuestoLinea
    from app.models.core import ObraSocial, Paciente
    from app.pacientes.models import Ficha
    from app.pagos.models import AprobacionPago, ConfiguracionSena, PagoSena
    from app.turnos.models import Turno

    async with session_factory() as session:
        for model in (
            PagoPresupuesto,
            PresupuestoLinea,
            Presupuesto,
            OdontogramaRegistro,
            Ficha,
            AprobacionPago,
            PagoSena,
            TokenBlacklist,
            RegistroAuditoria,
            UsuarioRol,
            Usuario,
            Rol,
            Turno,
            Paciente,
            ObraSocial,
            Profesional,
            Sillon,
            Tratamiento,
        ):
            await session.execute(delete(model))
        # Singleton de la seña: vuelve a los valores por defecto de la migración 006.
        await session.execute(update(ConfiguracionSena).values(
            sena_porcentaje=Decimal("30.00"), medios_habilitados=["mercadopago", "transferencia"],
            texto_politica_reembolso=POLITICA_REEMBOLSO_DEFECTO, expiracion_mp_minutos=30,
            expiracion_transferencia_minutos=1440, transferencia_alias=None, transferencia_cbu=None,
            transferencia_titular=None))
        await session.commit()
    yield


@pytest_asyncio.fixture
async def seed_ids(
    session_factory: async_sessionmaker[AsyncSession], clean_db: None
) -> dict[str, int]:
    """Insert one Profesional/Sillon/Tratamiento via ORM (fixture harness); return ids."""
    from decimal import Decimal

    async with session_factory() as session:
        prof = Profesional(nombre="Dra. Test", matricula="MAT-001", especialidad="General")
        sill = Sillon(nombre="S1", estado="activo")
        trat = Tratamiento(nombre="Limpieza", duracion_minutos=30, precio_base=Decimal("1000.00"))
        session.add_all([prof, sill, trat])
        await session.flush()
        await session.commit()
    return {"profesional_id": int(prof.id), "sillon_id": int(sill.id), "tratamiento_id": int(trat.id)}


@pytest_asyncio.fixture
async def seed_pair(
    session_factory: async_sessionmaker[AsyncSession], clean_db: None
) -> dict[str, int]:
    """Two profesionales + two sillones + one tratamiento via ORM (fixture harness)."""
    from decimal import Decimal

    async with session_factory() as session:
        p1 = Profesional(nombre="P1", matricula="M-1", especialidad="G")
        p2 = Profesional(nombre="P2", matricula="M-2", especialidad="G")
        s1 = Sillon(nombre="S1", estado="activo")
        s2 = Sillon(nombre="S2", estado="activo")
        t = Tratamiento(nombre="T", duracion_minutos=30, precio_base=Decimal("500.00"))
        session.add_all([p1, p2, s1, s2, t])
        await session.flush()
        await session.commit()
    return {
        "p1": int(p1.id),
        "p2": int(p2.id),
        "s1": int(s1.id),
        "s2": int(s2.id),
        "t": int(t.id),
    }


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """HTTP client bound to the FastAPI app via ASGI transport."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def future_iso(minutes_ahead: int = 60) -> str:
    """ISO-8601 UTC timestamp `minutes_ahead` in the future."""
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes_ahead)).isoformat()


def past_iso(minutes_back: int = 60) -> str:
    """ISO-8601 UTC timestamp `minutes_back` in the past."""
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_back)).isoformat()


@pytest_asyncio.fixture
async def pasarela() -> AsyncIterator["PasarelaEspia"]:
    """Sobreescribe ``get_pasarela`` con una pasarela falsa que registra llamadas (nunca hay red)."""
    from app.main import app
    from app.pagos.deps import get_pasarela
    from tests.sena_helpers import PasarelaEspia

    espia = PasarelaEspia()
    app.dependency_overrides[get_pasarela] = lambda: espia
    try:
        yield espia
    finally:
        app.dependency_overrides.pop(get_pasarela, None)


class NotificadorEspia:
    """Notificador de prueba (C-07): registra los eventos publicados y puede simular una caída."""

    def __init__(self) -> None:
        self.eventos: list = []
        self.falla = False

    async def publicar(self, evento) -> None:  # type: ignore[no-untyped-def]
        if self.falla:
            raise RuntimeError("publicador caído (simulado)")
        self.eventos.append(evento)


@pytest_asyncio.fixture
async def notificador() -> AsyncIterator[NotificadorEspia]:
    """Sobreescribe ``get_notificador`` con un espía (nunca se toca Redis ni Google Calendar)."""
    from app.gestion.deps import get_notificador
    from app.main import app

    espia = NotificadorEspia()
    app.dependency_overrides[get_notificador] = lambda: espia
    try:
        yield espia
    finally:
        app.dependency_overrides.pop(get_notificador, None)


@pytest_asyncio.fixture
async def reloj() -> AsyncIterator[Callable[[datetime], None]]:
    """Fija el 'ahora' del servidor para la ventana de 24 h (C-07): ``reloj(instante)``."""
    from app.gestion.deps import get_reloj
    from app.main import app

    def fijar(ahora: datetime) -> None:
        app.dependency_overrides[get_reloj] = lambda: ahora

    try:
        yield fijar
    finally:
        app.dependency_overrides.pop(get_reloj, None)


# ---------------------------------------------------------------------------
# C-08: usuarios del panel y tokens para los tests (datos sintéticos, R19)
# ---------------------------------------------------------------------------

PASSWORD_PANEL = "password-sintetica-123"
_HASH_PANEL: list[str] = []  # bcrypt con coste bajo, calculado una sola vez (acelera los tests)


def hash_panel() -> str:
    if not _HASH_PANEL:
        import bcrypt

        _HASH_PANEL.append(bcrypt.hashpw(PASSWORD_PANEL.encode(), bcrypt.gensalt(rounds=4)).decode())
    return _HASH_PANEL[0]


async def crear_usuario_panel(
    factory: async_sessionmaker[AsyncSession], email: str, roles: list[str], *,
    profesional_id: int | None = None,
) -> tuple[int, str]:
    """Crea (o reutiliza) un usuario con roles. Devuelve (usuario_id, access_token válido)."""
    from sqlalchemy import select

    from app.auth.service import create_access_token

    async with factory() as session:
        usuario = Usuario(email=email, nombre_completo="Usuario Sintético", hashed_password=hash_panel(),
                          profesional_id=profesional_id)
        session.add(usuario)
        await session.flush()
        for nombre in roles:
            rol = (await session.execute(select(Rol).where(Rol.nombre == nombre))).scalar_one_or_none()
            if rol is None:
                rol = Rol(nombre=nombre)
                session.add(rol)
                await session.flush()
            session.add(UsuarioRol(usuario_id=usuario.id, rol_id=rol.id))
        await session.commit()
        usuario_id = int(usuario.id)
    token = create_access_token({"sub": str(usuario_id), "roles": roles, "email": email,
                                 "jti": f"jti-{usuario_id}-{os.urandom(4).hex()}"})
    return usuario_id, token


@pytest_asyncio.fixture
async def token_recepcion(session_factory: async_sessionmaker[AsyncSession], clean_db: None) -> str:
    return (await crear_usuario_panel(session_factory, "recepcion@turnos.test", ["recepcion"]))[1]


@pytest_asyncio.fixture
async def token_admin(session_factory: async_sessionmaker[AsyncSession], clean_db: None) -> str:
    return (await crear_usuario_panel(session_factory, "admin@turnos.test", ["admin"]))[1]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def client_recepcion(client: AsyncClient, token_recepcion: str) -> AsyncClient:
    """Cliente HTTP ya autenticado como recepción (para los tests de la primitiva ``POST /api/turnos``)."""
    client.headers.update(bearer(token_recepcion))
    return client
