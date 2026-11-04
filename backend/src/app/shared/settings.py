"""Application settings (R17: secrets only via env vars)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded exclusively from environment (R17)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://turnos:turnos@localhost:5433/turnos"
    app_tz: str = "America/Argentina/Buenos_Aires"

    # JWT (R17: secret solo por env var, expiración corta + refresh)
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_minutes: int = 10080  # 7 días


def get_settings() -> Settings:
    """Return application settings from environment."""
    return Settings()
