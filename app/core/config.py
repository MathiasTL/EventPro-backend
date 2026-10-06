"""Configuración global de la aplicación (Twelve-Factor App) con Pydantic Settings.

Las variables se leen del entorno y, en desarrollo, del archivo `.env`. Los valores
por defecto permiten importar el paquete sin un `.env` presente (por ejemplo, en la
ejecución de las pruebas unitarias de dominio), salvo ``secret_key``, que exige una
cadena de al menos 32 caracteres.
"""

from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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

    # --- Almacenamiento de comprobantes/evidencias (E5) ---
    storage_backend: str = "local"
    local_storage_path: str = "./uploads"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    """Devuelve la instancia única de configuración."""

    return Settings()
