from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.input.event_extension_port import (
    IRegisterEventExtensionPort,
    ISettleEventPort,
)
from app.application.ports.input.event_schedule_port import IGetEventSchedulePort
from app.application.ports.input.event_start_port import IStartEventPort
from app.application.ports.output.audit_log_port import IAuditLogPort
from app.application.ports.output.cache_port import ICachePort
from app.application.ports.output.clock_port import IClockPort
from app.application.ports.output.crew_schedule_read_port import ICrewScheduleReadPort
from app.application.ports.output.payment_evidence_storage_port import IPaymentEvidenceStoragePort
from app.application.ports.output.payment_repository_port import IPaymentRepositoryPort
from app.application.ports.output.pre_show_payment_verification_port import (
    IPreShowPaymentVerificationPort,
)
from app.application.ports.output.quote_schedule_read_port import IQuoteScheduleReadPort
from app.application.ports.output.refresh_token_repository_port import IRefreshTokenRepositoryPort
from app.application.ports.output.repository_health_port import IRepositoryHealthPort
from app.application.ports.output.user_repository_port import IUserRepositoryPort
from app.application.services.audit_service import AuditService
from app.application.use_cases.auth.login import LoginUseCase
from app.application.use_cases.auth.logout import LogoutUseCase
from app.application.use_cases.auth.refresh import RefreshUseCase
from app.application.use_cases.event.get_event_schedule import GetEventScheduleUseCase
from app.application.use_cases.event.register_event_extension import RegisterEventExtensionUseCase
from app.application.use_cases.event.settle_event import SettleEventUseCase
from app.application.use_cases.event.start_event import StartEventUseCase
from app.application.use_cases.payment.audit_payment import AuditPaymentUseCase
from app.application.use_cases.payment.get_payment import GetPaymentUseCase
from app.application.use_cases.payment.get_payment_evidence import GetPaymentEvidenceUseCase
from app.application.use_cases.payment.list_payments import ListPaymentsUseCase
from app.application.use_cases.payment.refund_payment import RefundPaymentUseCase
from app.application.use_cases.payment.register_advance_payment import RegisterAdvancePaymentUseCase
from app.application.use_cases.payment.verify_payment import VerifyPaymentUseCase
from app.core.config import get_settings
from app.infrastructure.adapters.secondary.cache.redis_cache_adapter import RedisCacheAdapter
from app.infrastructure.adapters.secondary.external_services import (
    fake_payment_verification_adapter,
    system_clock_adapter,
)
from app.infrastructure.adapters.secondary.external_services.fake_schedule_adapters import (
    FakeCrewScheduleReadAdapter,
    FakeQuoteScheduleReadAdapter,
)
from app.infrastructure.adapters.secondary.persistence.audit_log_adapter import (
    SQLAlchemyAuditLogAdapter,
)
from app.infrastructure.adapters.secondary.persistence.database import (
    get_engine,
    get_session,
    get_sessionmaker,
)
from app.infrastructure.adapters.secondary.persistence.refresh_token_repository import (
    SQLAlchemyRefreshTokenRepository,
)
from app.infrastructure.adapters.secondary.persistence.repositories import (
    sqlalchemy_event_repository,
    sqlalchemy_payment_repository,
)
from app.infrastructure.adapters.secondary.persistence.sqlalchemy_health_adapter import (
    SQLAlchemyHealthAdapter,
)
from app.infrastructure.adapters.secondary.persistence.user_repository import (
    SQLAlchemyUserRepository,
)
from app.infrastructure.adapters.secondary.storage.local_evidence_storage import (
    LocalEvidenceStorage,
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


@lru_cache
def get_quote_schedule_read_port() -> IQuoteScheduleReadPort:
    return FakeQuoteScheduleReadAdapter()


@lru_cache
def get_crew_schedule_read_port() -> ICrewScheduleReadPort:
    return FakeCrewScheduleReadAdapter()


@lru_cache
def get_pre_show_payment_verification_port() -> IPreShowPaymentVerificationPort:
    return fake_payment_verification_adapter.FakePreShowPaymentVerificationAdapter()


@lru_cache
def get_clock_port() -> IClockPort:
    return system_clock_adapter.SystemClockAdapter()


def get_start_event_use_case(
    session: Annotated[AsyncSession, Depends(get_session)],
    payments: Annotated[
        IPreShowPaymentVerificationPort, Depends(get_pre_show_payment_verification_port)
    ],
    crews: Annotated[ICrewScheduleReadPort, Depends(get_crew_schedule_read_port)],
    clock: Annotated[IClockPort, Depends(get_clock_port)],
) -> IStartEventPort:
    return StartEventUseCase(
        sqlalchemy_event_repository.SqlAlchemyEventRepository(session), payments, crews, clock
    )


def get_event_schedule_use_case(
    session: Annotated[AsyncSession, Depends(get_session)],
    quotes: Annotated[IQuoteScheduleReadPort, Depends(get_quote_schedule_read_port)],
    crews: Annotated[ICrewScheduleReadPort, Depends(get_crew_schedule_read_port)],
) -> IGetEventSchedulePort:
    return GetEventScheduleUseCase(
        sqlalchemy_event_repository.SqlAlchemyEventRepository(session), quotes, crews
    )


@lru_cache
def get_extension_evidence_storage() -> IPaymentEvidenceStoragePort:
    return LocalEvidenceStorage(allowed_mime={"image/jpeg", "image/png", "image/webp"})


def get_register_event_extension_use_case(
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[IPaymentEvidenceStoragePort, Depends(get_extension_evidence_storage)],
    crews: Annotated[ICrewScheduleReadPort, Depends(get_crew_schedule_read_port)],
    clock: Annotated[IClockPort, Depends(get_clock_port)],
) -> IRegisterEventExtensionPort:
    return RegisterEventExtensionUseCase(
        sqlalchemy_event_repository.SqlAlchemyEventRepository(session),
        storage,
        crews,
        clock,
        simultaneous_threshold=get_settings().simultaneous_shows_threshold,
    )


def get_settle_event_use_case(
    session: Annotated[AsyncSession, Depends(get_session)],
    crews: Annotated[ICrewScheduleReadPort, Depends(get_crew_schedule_read_port)],
) -> ISettleEventPort:
    return SettleEventUseCase(sqlalchemy_event_repository.SqlAlchemyEventRepository(session), crews)


@lru_cache
def get_evidence_storage() -> LocalEvidenceStorage:
    return LocalEvidenceStorage()


def get_payment_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IPaymentRepositoryPort:
    return sqlalchemy_payment_repository.SqlAlchemyPaymentRepository(session)


def get_register_advance_payment_use_case(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RegisterAdvancePaymentUseCase:
    return RegisterAdvancePaymentUseCase(get_payment_repository(session))


def get_verify_payment_use_case(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> VerifyPaymentUseCase:
    return VerifyPaymentUseCase(get_payment_repository(session))


def get_audit_payment_use_case(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuditPaymentUseCase:
    return AuditPaymentUseCase(get_payment_repository(session), get_audit_service())


def get_refund_payment_use_case(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RefundPaymentUseCase:
    return RefundPaymentUseCase(get_payment_repository(session))


def get_list_payments_use_case(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ListPaymentsUseCase:
    return ListPaymentsUseCase(get_payment_repository(session))


def get_get_payment_use_case(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> GetPaymentUseCase:
    return GetPaymentUseCase(get_payment_repository(session))


def get_get_payment_evidence_use_case(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> GetPaymentEvidenceUseCase:
    return GetPaymentEvidenceUseCase(get_payment_repository(session), get_evidence_storage())


def clear_application_caches() -> None:
    """Suelta repositorios, servicios y casos de uso (sujetos al engine/loop activos)."""
    get_user_repository.cache_clear()
    get_refresh_token_repository.cache_clear()
    get_login_use_case.cache_clear()
    get_refresh_use_case.cache_clear()
    get_logout_use_case.cache_clear()
    get_audit_log_port.cache_clear()
    get_audit_service.cache_clear()
    get_evidence_storage.cache_clear()
    get_extension_evidence_storage.cache_clear()
    get_quote_schedule_read_port.cache_clear()
    get_crew_schedule_read_port.cache_clear()
    get_pre_show_payment_verification_port.cache_clear()
    get_clock_port.cache_clear()


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
