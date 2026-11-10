"""Application settings (R17: secrets only via env vars)."""

from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

JWT_SECRET_MIN_LENGTH = 32
ENTORNOS_CON_PASARELA_FALSA = ("test", "e2e")


class Settings(BaseSettings):
    """Runtime configuration loaded exclusively from environment (R17)."""

    # hide_input_in_errors: un secreto corto rechazado no debe quedar en el mensaje de error.
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", hide_input_in_errors=True
    )

    database_url: str = "postgresql+asyncpg://turnos:turnos@localhost:5433/turnos"
    app_tz: str = "America/Argentina/Buenos_Aires"

    # JWT (R17: secret solo por env var, expiración corta + refresh)
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_minutes: int = 10080  # 7 días

    @field_validator("jwt_secret_key")
    @classmethod
    def _jwt_secret_min_length(cls, value: str) -> str:
        """Reject empty or short secrets: HS256 needs at least 32 characters (R17)."""
        if len(value) < JWT_SECRET_MIN_LENGTH:
            raise ValueError(
                f"JWT_SECRET_KEY debe tener al menos {JWT_SECRET_MIN_LENGTH} caracteres"
            )
        return value

    # Seña y pagos (C-06; R17: credenciales solo por env var, nunca en el repo)
    # Defaults seguros (fail-safe): sin configuración explícita es producción con Mercado Pago real.
    app_env: Literal["development", "test", "e2e", "production"] = "production"
    mp_gateway: Literal["fake", "mercadopago"] = "mercadopago"
    mp_access_token: SecretStr | None = None
    mp_webhook_secret: SecretStr | None = None
    mp_api_base_url: str = "https://api.mercadopago.com"
    mp_webhook_tolerancia_segundos: int = 300
    public_base_url: str = "http://localhost:5173"  # back_urls del checkout
    api_public_base_url: str = "http://localhost:8000"  # notification_url del webhook
    sena_barrido_segundos: int = 60
    sena_barrido_habilitado: bool = True

    # Panel (C-08, O14): minutos después del inicio desde los que recepción puede marcar un turno ausente.
    ausente_tolerancia_minutos: int = Field(10, ge=0)

    @model_validator(mode="after")
    def _validar_pasarela(self) -> "Settings":
        """Mercado Pago exige credenciales; la pasarela falsa no puede correr en producción."""
        if self.mp_gateway == "fake" and self.app_env not in ENTORNOS_CON_PASARELA_FALSA:
            # Con la falsa cualquiera podría forjar un webhook y obtener un turno sin pagar.
            raise ValueError("MP_GATEWAY=fake solo está permitido con APP_ENV=test o APP_ENV=e2e")
        if self.mp_gateway == "mercadopago":
            if self.mp_access_token is None or not self.mp_access_token.get_secret_value():
                raise ValueError("MP_ACCESS_TOKEN es obligatoria cuando MP_GATEWAY=mercadopago")
            if self.mp_webhook_secret is None or not self.mp_webhook_secret.get_secret_value():
                raise ValueError("MP_WEBHOOK_SECRET es obligatoria cuando MP_GATEWAY=mercadopago")
        return self


def get_settings() -> Settings:
    """Return application settings from environment."""
    return Settings()
