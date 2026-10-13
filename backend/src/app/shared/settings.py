"""Application settings (R17: secrets only via env vars)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded exclusively from environment."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://turnos:turnos@localhost:5433/turnos"
    app_tz: str = "America/Argentina/Buenos_Aires"


def get_settings() -> Settings:
    """Return application settings from environment."""
    return Settings()
