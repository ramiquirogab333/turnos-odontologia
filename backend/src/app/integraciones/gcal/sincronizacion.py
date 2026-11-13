"""Trabajo ``gcal_sync`` (C-10, D4, O4, O13): por conexión activa -> lock -> token -> pull -> conflictos -> push.

Corre en el worker: la API nunca llama a Google (R16). Cada conexión se procesa en su propia sesión y transacción con un
``pg_try_advisory_xact_lock`` por conexión (si otro worker la tiene, se saltea). Un error en una conexión no corta las
demás. Un error transitorio deja los cambios pendientes y reintenta con espera creciente (1, 5, 15 y 60 minutos);
``invalid_grant`` (o un token ilegible) deja la conexión ``revocada``. Ningún log lleva datos personales ni tokens.
"""

from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integraciones.gcal.cifrado import TokenIlegible, cifrar, descifrar
from app.integraciones.gcal.conflictos import sincronizar_conflictos
from app.integraciones.gcal.models import GcalConexion
from app.integraciones.gcal.proveedor import AccesoRevocado, ErrorProveedor, ProveedorCalendario
from app.integraciones.gcal.pull import pull
from app.integraciones.gcal.reconciliacion import reconciliar_push
from app.models.core import RegistroAuditoria
from app.shared.logger import get_logger
from app.shared.settings import Settings, get_settings

logger = get_logger(__name__)

LOCK_GCAL = 5_005_010  # clave arbitraria del advisory lock por conexión (par: clave, conexion_id)
BACKOFF_MINUTOS = (1, 5, 15, 60)
MARGEN_TOKEN = timedelta(seconds=60)


def espera_tras_fallo(fallos: int) -> timedelta:
    """Espera antes del próximo intento tras ``fallos`` fallos consecutivos (1, 5, 15, 60 min como máximo)."""
    return timedelta(minutes=BACKOFF_MINUTOS[min(max(fallos, 1), len(BACKOFF_MINUTOS)) - 1])


async def sincronizar_calendarios(factory: async_sessionmaker[AsyncSession], proveedor: ProveedorCalendario,
                                  ahora: datetime, ajustes: Settings | None = None) -> int:
    """Un ciclo sobre todas las conexiones activas listas. Devuelve cuántas terminaron bien."""
    ajustes = ajustes or get_settings()
    if not ajustes.gcal_configurado:
        return 0
    async with factory() as session:
        ids = [int(i) for i in (await session.execute(select(GcalConexion.id).where(
            GcalConexion.estado == "activa",
            or_(GcalConexion.proximo_intento_en.is_(None), GcalConexion.proximo_intento_en <= ahora))
            .order_by(GcalConexion.id))).scalars()]
    correctas = 0
    for conexion_id in ids:
        try:
            async with factory() as session:
                if await _sincronizar_conexion(session, conexion_id, proveedor, ahora, ajustes):
                    correctas += 1
        except Exception as error:  # noqa: BLE001 - una conexión fallida no debe cortar a las demás
            logger.error("gcal_sync: conexión %d fallida (%s)", conexion_id, type(error).__name__)
    return correctas


async def _acceso_vigente(conexion: GcalConexion, proveedor: ProveedorCalendario, ahora: datetime, clave: str) -> str:
    """Access token descifrado; si venció (o falta), lo renueva con el refresh token y lo guarda cifrado."""
    if (conexion.access_token_cifrado and conexion.access_expira_en is not None
            and conexion.access_expira_en > ahora + MARGEN_TOKEN):
        return descifrar(conexion.access_token_cifrado, clave)
    tokens = await proveedor.renovar_token(descifrar(conexion.refresh_token_cifrado or "", clave))
    conexion.access_token_cifrado = cifrar(tokens.access_token, clave)
    conexion.access_expira_en = tokens.expira_en
    return tokens.access_token


async def _sincronizar_conexion(session: AsyncSession, conexion_id: int, proveedor: ProveedorCalendario,
                                ahora: datetime, ajustes: Settings) -> bool:
    obtuvo = (await session.execute(select(func.pg_try_advisory_xact_lock(LOCK_GCAL, conexion_id)))).scalar_one()
    if not obtuvo:
        await session.rollback()
        return False  # otro worker la está procesando
    conexion = (await session.execute(select(GcalConexion).where(GcalConexion.id == conexion_id)
                                      .execution_options(populate_existing=True))).scalar_one_or_none()
    if conexion is None or conexion.estado != "activa":
        await session.rollback()
        return False
    clave = ajustes.gcal_token_clave.get_secret_value() if ajustes.gcal_token_clave else ""
    try:
        acceso = await _acceso_vigente(conexion, proveedor, ahora, clave)
        await pull(session, conexion, proveedor, acceso, ahora, ajustes)
        await sincronizar_conflictos(session, conexion, ahora)
        await reconciliar_push(session, conexion, proveedor, acceso, ahora, ajustes)
        await sincronizar_conflictos(session, conexion, ahora)
    except (AccesoRevocado, TokenIlegible) as fallo:
        await _marcar_revocada(session, conexion, fallo)
        return False
    except ErrorProveedor as fallo:
        await _registrar_fallo(session, conexion, fallo, ahora)
        return False
    conexion.fallos_consecutivos, conexion.proximo_intento_en, conexion.ultimo_error = 0, None, None
    conexion.ultimo_sync_ok_en = ahora
    await session.commit()
    return True


async def _marcar_revocada(session: AsyncSession, conexion: GcalConexion, fallo: Exception) -> None:
    conexion_id = conexion.id
    await session.rollback()
    conexion = (await session.execute(select(GcalConexion).where(GcalConexion.id == conexion_id)
                                      .execution_options(populate_existing=True))).scalar_one()
    conexion.estado, conexion.proximo_intento_en = "revocada", None
    conexion.ultimo_error = type(fallo).__name__
    session.add(RegistroAuditoria(  # sin usuario (lo hizo el sistema) y sin tokens
        usuario_id=None, accion="UPDATE", entidad="gcal_conexion", entidad_id=str(conexion.id),
        datos_despues={"profesional_id": conexion.profesional_id, "estado": "revocada", "origen": "invalid_grant"},
        ip=None))
    await session.commit()
    logger.warning("gcal_sync: conexión %d revocada (%s)", conexion.id, type(fallo).__name__)


async def _registrar_fallo(session: AsyncSession, conexion: GcalConexion, fallo: ErrorProveedor, ahora: datetime) -> None:
    """Conserva lo ya hecho (cada llamada exitosa quedó vinculada) y programa el reintento con espera creciente."""
    conexion.fallos_consecutivos += 1
    conexion.proximo_intento_en = ahora + espera_tras_fallo(conexion.fallos_consecutivos)
    conexion.ultimo_error = f"{type(fallo).__name__} {fallo.codigo if fallo.codigo is not None else 'red'}"[:300]
    await session.commit()
    logger.warning("gcal_sync: conexión %d con error (%s); reintento %s", conexion.id, conexion.ultimo_error,
                   conexion.proximo_intento_en.isoformat())
