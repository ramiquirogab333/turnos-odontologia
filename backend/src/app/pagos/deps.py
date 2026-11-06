"""Inyección de la pasarela de pagos (D1). Los tests la sobreescriben con ``dependency_overrides``."""

from app.pagos.fake import FakePasarela
from app.pagos.mercadopago import MercadoPagoPasarela
from app.pagos.pasarela import PasarelaPagos
from app.shared.settings import get_settings


def get_pasarela() -> PasarelaPagos:
    """Pasarela según ``MP_GATEWAY``: real (credenciales por env, R17) o falsa (solo test/E2E)."""
    s = get_settings()
    if s.mp_gateway == "mercadopago":
        assert s.mp_access_token is not None  # garantizado por Settings
        return MercadoPagoPasarela(
            access_token=s.mp_access_token.get_secret_value(), api_base_url=s.mp_api_base_url,
            public_base_url=s.public_base_url, api_public_base_url=s.api_public_base_url)
    return FakePasarela(s.public_base_url)
