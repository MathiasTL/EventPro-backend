from functools import lru_cache

from redis.asyncio import Redis

from app.application.ports.output.audit_log_port import IAuditLogPort
from app.application.ports.output.cache_port import ICachePort
from app.application.ports.output.refresh_token_repository_port import IRefreshTokenRepositoryPort
from app.application.ports.output.repository_health_port import IRepositoryHealthPort
from app.application.ports.output.user_repository_port import IUserRepositoryPort
from app.application.services.audit_service import AuditService
from app.application.use_cases.auth.login import LoginUseCase
from app.application.use_cases.auth.logout import LogoutUseCase
from app.application.use_cases.auth.refresh import RefreshUseCase
from app.core.config import get_settings
from app.infrastructure.adapters.secondary.cache.redis_cache_adapter import RedisCacheAdapter
from app.infrastructure.adapters.secondary.persistence.audit_log_adapter import (
    SQLAlchemyAuditLogAdapter,
)
from app.infrastructure.adapters.secondary.persistence.database import get_engine, get_sessionmaker
from app.infrastructure.adapters.secondary.persistence.refresh_token_repository import (
    SQLAlchemyRefreshTokenRepository,
)
from app.infrastructure.adapters.secondary.persistence.sqlalchemy_health_adapter import (
    SQLAlchemyHealthAdapter,
)
from app.infrastructure.adapters.secondary.persistence.user_repository import (
    SQLAlchemyUserRepository,
)


@lru_cache
def get_redis_client() -> Redis:
    settings = get_settings()
    return Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        password=settings.redis_password or None,
    )


@lru_cache
def get_repository_health_port() -> IRepositoryHealthPort:
    return SQLAlchemyHealthAdapter(get_engine())


@lru_cache
def get_cache_port() -> ICachePort:
    return RedisCacheAdapter(get_redis_client())


@lru_cache
def get_user_repository() -> IUserRepositoryPort:
    return SQLAlchemyUserRepository(get_sessionmaker())


@lru_cache
def get_refresh_token_repository() -> IRefreshTokenRepositoryPort:
    return SQLAlchemyRefreshTokenRepository(get_sessionmaker())


@lru_cache
def get_login_use_case() -> LoginUseCase:
    settings = get_settings()
    return LoginUseCase(
        get_user_repository(),
        get_refresh_token_repository(),
        secret_key=settings.secret_key,
        access_expire_minutes=settings.access_token_expire_minutes,
        refresh_expire_days=settings.refresh_token_expire_days,
    )


@lru_cache
def get_refresh_use_case() -> RefreshUseCase:
    settings = get_settings()
    return RefreshUseCase(
        get_user_repository(),
        get_refresh_token_repository(),
        secret_key=settings.secret_key,
        access_expire_minutes=settings.access_token_expire_minutes,
        refresh_expire_days=settings.refresh_token_expire_days,
    )


@lru_cache
def get_logout_use_case() -> LogoutUseCase:
    return LogoutUseCase(get_refresh_token_repository())


@lru_cache
def get_audit_log_port() -> IAuditLogPort:
    return SQLAlchemyAuditLogAdapter(get_sessionmaker())


@lru_cache
def get_audit_service() -> AuditService:
    return AuditService(get_audit_log_port())


def clear_application_caches() -> None:
    """Suelta repositorios, servicios y casos de uso (sujetos al engine/loop activos)."""
    get_user_repository.cache_clear()
    get_refresh_token_repository.cache_clear()
    get_login_use_case.cache_clear()
    get_refresh_use_case.cache_clear()
    get_logout_use_case.cache_clear()
    get_audit_log_port.cache_clear()
    get_audit_service.cache_clear()


async def shutdown_infrastructure() -> None:
    if get_engine.cache_info().currsize:
        await get_engine().dispose()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    if get_redis_client.cache_info().currsize:
        await get_redis_client().aclose()
    get_redis_client.cache_clear()
    get_repository_health_port.cache_clear()
    get_cache_port.cache_clear()
    clear_application_caches()
