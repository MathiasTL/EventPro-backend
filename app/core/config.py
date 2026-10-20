"""Configuración global de la aplicación (Twelve-Factor App) con Pydantic Settings.

Las variables se leen del entorno y, en desarrollo, del archivo `.env`. Los valores
por defecto permiten importar el paquete sin un `.env` presente (por ejemplo, en la
ejecución de las pruebas unitarias de dominio), salvo ``secret_key``, que exige una
cadena de al menos 32 caracteres.
"""

from decimal import Decimal
from functools import lru_cache
from typing import Annotated, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Entornos donde la configuración de Chatwoot (incluido el secreto del webhook) es obligatoria.
_CHATWOOT_REQUIRED_ENVIRONMENTS = frozenset({"staging", "production"})


class Settings(BaseSettings):
    """Ajustes de la aplicación EventPro."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        validate_default=True,
    )

    # --- Aplicación y servidor ---
    app_env: str = "development"
    app_name: str = "EventPro-Backend"
    api_v1_prefix: str = "/api/v1"
    port: int = 8000
    debug: bool = False
    log_level: str = "INFO"

    secret_key: str = Field(default="", min_length=32)
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7
    cors_origins: Annotated[list[str], NoDecode] = []

    # 127.0.0.1 en localhost: en Windows el resolve a ::1 (IPv6) tarda ~2 s en
    # rechazarse con Docker Desktop, y rompe el timeout de 2 s del /health.
    database_url: str = (
        "postgresql+asyncpg://eventpro_user:eventpro_secret_password@127.0.0.1:5432/eventpro_db"
    )
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0

    superadmin_email: str = "admin@eventpro.pe"
    superadmin_password: str = "admin123"

    # --- Reglas de negocio configurables (E3) ---
    simultaneous_shows_threshold: int = 3
    advance_percent: int = 10
    transit_rest_buffer_minutes: int = 30

    # --- Cotización y movilidad (E1, valores aprobados por el negocio, RN-03) ---
    advance_deadline_hours: int = Field(default=24, gt=0)
    mobility_rate_per_km: Decimal = Field(default=Decimal("1.00"), ge=0, decimal_places=2)
    mobility_rate_per_minute: Decimal = Field(default=Decimal("0.30"), ge=0, decimal_places=2)
    mobility_minimum_amount: Decimal = Field(default=Decimal("20.00"), ge=0, decimal_places=2)
    mobility_margin_percent: Decimal = Field(default=Decimal("15"), ge=0)
    mobility_zone_1_amount: Decimal = Field(default=Decimal("25.00"), ge=0, decimal_places=2)
    mobility_zone_2_amount: Decimal = Field(default=Decimal("45.00"), ge=0, decimal_places=2)
    mobility_zone_3_amount: Decimal = Field(default=Decimal("70.00"), ge=0, decimal_places=2)

    # --- Cola de mensajes salientes / outbox (E1, RNF-03.2) ---
    outbox_batch_size: int = Field(default=20, gt=0)
    # Debe superar el tiempo máximo de un ciclo de despacho; si no, el lote se reenvía.
    outbox_lease_seconds: int = Field(default=60, gt=0)
    outbox_max_attempts: int = Field(default=6, gt=0)

    # --- Gateway de WhatsApp vía Chatwoot (E1) ---
    # Vacío = adaptador simulado. Con URL base, el resto de la configuración es obligatoria.
    chatwoot_base_url: str = ""
    chatwoot_account_id: int | None = None
    chatwoot_inbox_id: int | None = None
    chatwoot_bot_token: SecretStr = SecretStr("")
    chatwoot_agent_token: SecretStr = SecretStr("")
    chatwoot_webhook_secret: SecretStr = SecretStr("")
    # Un envío encadena hasta cuatro llamadas; 4 x timeout debe caber en el ciclo del worker.
    chatwoot_timeout_seconds: float = Field(default=10.0, gt=0)
    chatwoot_connect_timeout_seconds: float = Field(default=3.0, gt=0)
    chatwoot_template_language: str = "es"
    chatwoot_template_category: str = "UTILITY"

    # --- Agente conversacional con OpenAI (E1) ---
    # Sin clave el bot usa el motor de menús; con clave, el agente es el motor principal.
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-6-luna"
    openai_timeout_seconds: float = Field(default=15.0, gt=0)

    # --- Almacenamiento de comprobantes/evidencias (E5) ---
    storage_backend: str = "local"
    local_storage_path: str = "./uploads"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("chatwoot_account_id", "chatwoot_inbox_id", mode="before")
    @classmethod
    def _blank_id_is_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("chatwoot_base_url", mode="after")
    @classmethod
    def _normalize_chatwoot_base_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if value and not value.startswith(("http://", "https://")):
            raise ValueError("CHATWOOT_BASE_URL debe comenzar con http:// o https://")
        return value

    @property
    def chatwoot_enabled(self) -> bool:
        """El adaptador real de Chatwoot se activa al definir la URL base."""

        return bool(self.chatwoot_base_url)

    @property
    def openai_enabled(self) -> bool:
        """El agente de OpenAI se activa al definir una clave no vacía."""

        return self.openai_api_key is not None and bool(
            self.openai_api_key.get_secret_value().strip()
        )

    @model_validator(mode="after")
    def _chatwoot_configuration_is_complete(self) -> Self:
        # En staging y producción la mensajería real es obligatoria: el adaptador simulado
        # marcaría SENT mensajes que nunca llegan a WhatsApp, y el webhook sin secreto no firma.
        strict = self.app_env in _CHATWOOT_REQUIRED_ENVIRONMENTS
        if not (self.chatwoot_enabled or strict):
            return self
        required = {
            "CHATWOOT_BASE_URL": self.chatwoot_enabled,
            "CHATWOOT_ACCOUNT_ID": self.chatwoot_account_id is not None,
            "CHATWOOT_INBOX_ID": self.chatwoot_inbox_id is not None,
            "CHATWOOT_BOT_TOKEN": bool(self.chatwoot_bot_token.get_secret_value()),
            "CHATWOOT_AGENT_TOKEN": bool(self.chatwoot_agent_token.get_secret_value()),
        }
        if strict:
            required["CHATWOOT_WEBHOOK_SECRET"] = bool(
                self.chatwoot_webhook_secret.get_secret_value()
            )
        missing = [name for name, present in required.items() if not present]
        if missing:
            scope = f"APP_ENV={self.app_env}" if strict else "CHATWOOT_BASE_URL"
            raise ValueError(f"{scope} requiere definir también: " + ", ".join(missing))
        return self


@lru_cache
def get_settings() -> Settings:
    """Devuelve la instancia única de configuración."""

    return Settings()
