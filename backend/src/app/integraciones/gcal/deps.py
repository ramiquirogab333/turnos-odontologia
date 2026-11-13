"""Dependencias inyectables de la integración con Google Calendar. Los tests las sobreescriben con ``dependency_overrides``."""

from app.integraciones.gcal.proveedor import ProveedorCalendario
from app.integraciones.gcal.proveedor_http import ProveedorHttp
from app.shared.settings import get_settings


def get_proveedor() -> ProveedorCalendario:
    """Proveedor real contra Google (o contra el servidor falso si ``APP_ENV`` es test/e2e). Solo el canje OAuth lo usa en la API."""
    return ProveedorHttp.desde_ajustes(get_settings())
