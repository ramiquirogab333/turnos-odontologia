"""Application settings (R17: secrets only via env vars)."""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

JWT_SECRET_MIN_LENGTH = 32


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


def get_settings() -> Settings:
    """Return application settings from environment."""
    return Settings()
