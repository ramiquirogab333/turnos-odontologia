"""Application settings (R17: secrets only via env vars)."""

import ipaddress
import re
from datetime import timedelta
from typing import Annotated, Literal

from cryptography.fernet import Fernet
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

JWT_SECRET_MIN_LENGTH = 32
ENTORNOS_CON_PASARELA_FALSA = ("test", "e2e")
GCAL_OAUTH_BASE_URL_GOOGLE = "https://accounts.google.com"
GCAL_API_BASE_URL_GOOGLE = "https://www.googleapis.com"
GCAL_TOKEN_BASE_URL_GOOGLE = "https://oauth2.googleapis.com"


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
    sena_barrido_segundos: int = Field(60, gt=0)
    sena_barrido_habilitado: bool = True

    # Panel (C-08, O14): minutos después del inicio desde los que recepción puede marcar un turno ausente.
    ausente_tolerancia_minutos: int = Field(10, ge=0)

    # C-09 (D8): trabajos programados, recordatorios y WhatsApp manual v1. Sin secretos (R17).
    redis_url: str = "redis://localhost:6379/0"
    reminder_lead_time: int = 48  # horas; acepta "48" y "48h" (O5)
    recordatorios_habilitado: bool = True
    recordatorios_intervalo_segundos: int = Field(300, gt=0)
    whatsapp_proveedor: Literal["manual", "falso"] = "manual"
    clinica_nombre: str = Field("la clínica", min_length=1, max_length=80)
    sena_barrido_en_api: bool = False  # O11: el barrido corre en el worker; la API solo si se habilita

    # C-10 (D10): Google Calendar. Credenciales y clave de cifrado solo por entorno (R17).
    gcal_client_id: str | None = None
    gcal_client_secret: SecretStr | None = None
    gcal_redirect_uri: str = "http://localhost:8000/api/panel/google-calendar/oauth/callback"
    gcal_token_clave: SecretStr | None = None
    gcal_sync_habilitado: bool = True
    gcal_sync_intervalo_segundos: int = Field(60, gt=0)
    gcal_horizonte_dias: int = Field(60, ge=1, le=365)
    public_panel_url: str = "http://localhost:5174"
    gcal_oauth_base_url: str = GCAL_OAUTH_BASE_URL_GOOGLE
    gcal_api_base_url: str = GCAL_API_BASE_URL_GOOGLE
    # Canje y revocación de tokens (otro host que el del consentimiento): en E2E el consentimiento lo abre el
    # navegador del host y el canje lo hace el contenedor, así que tienen URLs distintas.
    gcal_token_base_url: str = GCAL_TOKEN_BASE_URL_GOOGLE

    # C-15 (D3, D5, D6, D8): sesión del panel, límites de solicitudes, IP real y purga. Sin secretos (R17).
    sesion_maxima_horas: int = Field(12, ge=1, le=168)
    rate_limit_login_ip_email_max: int = Field(5, gt=0)
    rate_limit_login_ip_email_ventana_seg: int = Field(900, gt=0)
    rate_limit_login_ip_max: int = Field(30, gt=0)
    rate_limit_login_ip_ventana_seg: int = Field(900, gt=0)
    rate_limit_login_email_max: int = Field(20, gt=0)
    rate_limit_login_email_ventana_seg: int = Field(3600, gt=0)
    rate_limit_refresh_ip_max: int = Field(60, gt=0)
    rate_limit_refresh_ip_ventana_seg: int = Field(900, gt=0)
    rate_limit_publico_escritura_max: int = Field(10, gt=0)
    rate_limit_publico_escritura_ventana_seg: int = Field(600, gt=0)
    rate_limit_publico_lectura_max: int = Field(120, gt=0)
    rate_limit_publico_lectura_ventana_seg: int = Field(60, gt=0)
    rate_limit_timeout_ms: int = Field(200, gt=0)
    # Lista separada por comas de IPs o CIDR; vacía = no confiar en ninguna cabecera X-Forwarded-For (O10).
    trusted_proxies: Annotated[list[str], NoDecode] = Field(default_factory=list)
    purga_sesiones_habilitado: bool = True
    purga_sesiones_intervalo_segundos: int = Field(3600, gt=0)
    purga_sesiones_margen_minutos: int = Field(60, ge=0)
    # C-13 (D10, O15): tope de exportaciones por usuario y hora, y tiempo máximo de una exportación (y de su lease).
    export_max_por_hora: int = Field(20, gt=0)
    export_timeout_segundos: int = Field(300, gt=0)

    @field_validator("trusted_proxies", mode="before")
    @classmethod
    def _parsear_proxies_confiables(cls, value: object) -> object:
        """Acepta ``"192.0.2.1, 198.51.100.0/24"``; rechaza basura y las redes que confían en todo el mundo."""
        if isinstance(value, str):
            value = [parte.strip() for parte in value.split(",") if parte.strip()]
        if not isinstance(value, list):
            return value
        for entrada in value:
            try:
                red = ipaddress.ip_network(str(entrada), strict=False)
            except ValueError:
                raise ValueError(f"TRUSTED_PROXIES tiene una entrada que no es una IP ni un CIDR: {entrada!r}") from None
            if red.prefixlen == 0:
                raise ValueError("TRUSTED_PROXIES no puede incluir 0.0.0.0/0 ni ::/0: confiaría en cualquier cliente")
        return value

    @field_validator("reminder_lead_time", mode="before")
    @classmethod
    def _parsear_anticipacion(cls, value: object) -> object:
        """Acepta ``48`` o ``48h`` (horas) y exige un valor positivo."""
        if isinstance(value, str):
            coincidencia = re.fullmatch(r"\s*(\d+)\s*[hH]?\s*", value)
            if coincidencia is None:
                raise ValueError("REMINDER_LEAD_TIME debe ser un número de horas, p. ej. 48 o 48h")
            value = int(coincidencia.group(1))
        if isinstance(value, int) and value <= 0:
            raise ValueError("REMINDER_LEAD_TIME debe ser mayor que cero")
        return value

    @property
    def anticipacion_recordatorio(self) -> timedelta:
        """Anticipación con la que se generan los recordatorios."""
        return timedelta(hours=self.reminder_lead_time)

    @property
    def gcal_configurado(self) -> bool:
        """Hay credenciales de Google suficientes para conectar y sincronizar (sin ellas la API arranca igual)."""
        return bool(self.gcal_client_id and self.gcal_client_secret and self.gcal_client_secret.get_secret_value()
                    and self.gcal_token_clave and self.gcal_token_clave.get_secret_value())

    @model_validator(mode="after")
    def _validar_gcal(self) -> "Settings":
        """La clave Fernet es obligatoria y válida con ``GCAL_CLIENT_ID``; las URLs de Google solo se cambian en pruebas."""
        if self.gcal_client_id:
            clave = self.gcal_token_clave.get_secret_value() if self.gcal_token_clave else ""
            if not clave:
                raise ValueError("GCAL_TOKEN_CLAVE es obligatoria cuando hay GCAL_CLIENT_ID")
            try:
                Fernet(clave.encode())
            except (ValueError, TypeError):
                raise ValueError("GCAL_TOKEN_CLAVE no es una clave Fernet válida (32 bytes en base64)") from None
        distintas = (self.gcal_oauth_base_url != GCAL_OAUTH_BASE_URL_GOOGLE
                     or self.gcal_api_base_url != GCAL_API_BASE_URL_GOOGLE
                     or self.gcal_token_base_url != GCAL_TOKEN_BASE_URL_GOOGLE)
        if distintas and self.app_env not in ENTORNOS_CON_PASARELA_FALSA:
            raise ValueError("GCAL_OAUTH_BASE_URL, GCAL_TOKEN_BASE_URL y GCAL_API_BASE_URL distintas de Google "
                             "solo con APP_ENV=test o e2e")
        return self

    @model_validator(mode="after")
    def _validar_proveedor_whatsapp(self) -> "Settings":
        """El proveedor falso es solo de pruebas: nunca fuera de APP_ENV=test."""
        if self.whatsapp_proveedor == "falso" and self.app_env != "test":
            raise ValueError("WHATSAPP_PROVEEDOR=falso solo está permitido con APP_ENV=test")
        return self

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
