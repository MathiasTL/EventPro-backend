"""Configuración global de la aplicación (Twelve-Factor App) con Pydantic Settings.

Las variables se leen del entorno y, en desarrollo, del archivo `.env`. Los valores
por defecto permiten importar el paquete sin un `.env` presente (por ejemplo, en la
ejecución de las pruebas unitarias de dominio).
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Ajustes de la aplicación EventPro."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Aplicación y servidor ---
    app_env: str = "development"
    app_name: str = "EventPro-Backend"
    api_v1_prefix: str = "/api/v1"
    port: int = 8000
    debug: bool = True
    log_level: str = "INFO"
    secret_key: str = "change-me-with-at-least-32-random-characters"
    cors_origins: str = "http://localhost:3000"

    # --- Base de datos ---
    database_url: str = (
        "postgresql+asyncpg://eventpro_user:eventpro_secret_password@localhost:5432/eventpro_db"
    )

    # --- Redis ---
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0

    # --- Almacenamiento ---
    storage_backend: str = "local"
    local_storage_path: str = "./uploads"

    # --- Reglas de negocio configurables ---
    simultaneous_shows_threshold: int = 3
    advance_percent: int = 10
    transit_rest_buffer_minutes: int = 30


@lru_cache
def get_settings() -> Settings:
    """Devuelve la instancia única de configuración."""

    return Settings()


settings = get_settings()
