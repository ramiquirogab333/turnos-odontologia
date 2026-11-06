"""Acceso a la configuración singleton de la seña (RN-SN-03, RN-SN-07)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.pagos.models import ConfiguracionSena


async def obtener_configuracion(session: AsyncSession) -> ConfiguracionSena:
    """Fila única ``configuracion_sena`` (id = 1, sembrada por la migración 006)."""
    return (await session.execute(select(ConfiguracionSena).where(ConfiguracionSena.id == 1))).scalar_one()


def medios_disponibles(config: ConfiguracionSena) -> list[str]:
    """Medios que el paciente puede usar: la transferencia exige alias y CBU cargados por el admin."""
    transferencia_lista = bool(config.transferencia_alias and config.transferencia_cbu)
    return [m for m in config.medios_habilitados if m != "transferencia" or transferencia_lista]
