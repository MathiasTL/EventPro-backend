from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", validate_default=True)

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

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
