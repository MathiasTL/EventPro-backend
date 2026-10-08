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
from app.application.ports.output.availability_port import IAvailabilityPort
from app.application.ports.output.cache_port import ICachePort
from app.application.ports.output.catalog_admin_port import ICatalogAdminPort, ICrewAdminPort
from app.application.ports.output.catalog_read_port import ICatalogReadPort
from app.application.ports.output.client_repository_port import IClientRepositoryPort
from app.application.ports.output.clock_port import IClockPort
from app.application.ports.output.crew_schedule_read_port import ICrewScheduleReadPort
from app.application.ports.output.manual_booking_port import IBookingDocuments, IManualBookingStore
from app.application.ports.output.messaging_port import IMessagingPort
from app.application.ports.output.payment_evidence_storage_port import IPaymentEvidenceStoragePort
from app.application.ports.output.payment_repository_port import IPaymentRepositoryPort
from app.application.ports.output.pre_show_payment_verification_port import (
    IPreShowPaymentVerificationPort,
)
from app.application.ports.output.quote_repository_port import IQuoteRepositoryPort
from app.application.ports.output.quote_schedule_read_port import IQuoteScheduleReadPort
from app.application.ports.output.refresh_token_repository_port import IRefreshTokenRepositoryPort
from app.application.ports.output.repository_health_port import IRepositoryHealthPort
from app.application.ports.output.route_estimator_port import IRouteEstimatorPort
from app.application.ports.output.user_repository_port import IUserRepositoryPort
from app.application.services.audit_service import AuditService
from app.application.use_cases.audit.list_audit_logs import ListAuditLogsUseCase
from app.application.use_cases.auth.login import LoginUseCase
from app.application.use_cases.auth.logout import LogoutUseCase
from app.application.use_cases.auth.refresh import RefreshUseCase
from app.application.use_cases.catalog.manage_catalog import ManageCatalogUseCase
from app.application.use_cases.crew.manage_crews import ManageCrewsUseCase
from app.application.use_cases.event.get_event_schedule import GetEventScheduleUseCase
from app.application.use_cases.event.register_event_extension import RegisterEventExtensionUseCase
from app.application.use_cases.event.settle_event import SettleEventUseCase
from app.application.use_cases.event.start_event import StartEventUseCase
from app.application.use_cases.payment.approve_overbooked_payment import (
    ApproveOverbookedPaymentUseCase,
)
from app.application.use_cases.payment.audit_payment import AuditPaymentUseCase
from app.application.use_cases.payment.get_payment import GetPaymentUseCase
from app.application.use_cases.payment.get_payment_evidence import GetPaymentEvidenceUseCase
from app.application.use_cases.payment.list_payments import ListPaymentsUseCase
from app.application.use_cases.payment.refund_payment import RefundPaymentUseCase
from app.application.use_cases.payment.register_advance_payment import RegisterAdvancePaymentUseCase
from app.application.use_cases.payment.verify_payment import VerifyPaymentUseCase
from app.application.use_cases.quote.confirm_manual_booking import ConfirmManualBookingUseCase
from app.application.use_cases.quote.prepare_budget import PrepareBudgetUseCase
from app.application.use_cases.quote.refund_manual_booking import RefundManualBookingUseCase
from app.application.use_cases.quote.register_manual_booking import RegisterManualBookingUseCase
from app.application.use_cases.users.create_user import CreateUserUseCase
from app.application.use_cases.users.get_user import GetUserUseCase
from app.application.use_cases.users.list_users import ListUsersUseCase
from app.application.use_cases.users.update_user import UpdateUserUseCase
from app.core.config import get_settings
from app.domain.services.concurrency_evaluator import ConcurrencyEvaluator
from app.domain.services.financial_engine import FinancialEngine
from app.domain.services.inventory_availability import InventoryAvailabilityService
from app.domain.services.travel_interval_service import TravelIntervalService
from app.domain.value_objects.mobility import MobilityTariff
from app.infrastructure.adapters.secondary.availability.availability_adapter import (
    AvailabilityAdapter,
)
from app.infrastructure.adapters.secondary.cache.redis_cache_adapter import RedisCacheAdapter
from app.infrastructure.adapters.secondary.cache.redis_lock_adapter import RedisLockAdapter
from app.infrastructure.adapters.secondary.external_services import (
    fake_payment_verification_adapter,
    system_clock_adapter,
)
from app.infrastructure.adapters.secondary.external_services.fake_messaging_adapter import (
    FakeMessagingAdapter,
)
from app.infrastructure.adapters.secondary.external_services.fake_route_estimator_adapter import (
    FakeRouteEstimatorAdapter,
)
from app.infrastructure.adapters.secondary.external_services.fake_schedule_adapters import (
    FakeCrewScheduleReadAdapter,
    FakeQuoteScheduleReadAdapter,
)
from app.infrastructure.adapters.secondary.mobility.tariff import build_mobility_tariff
from app.infrastructure.adapters.secondary.persistence import (
    SqlAlchemyAvailabilityRepository,
    SqlAlchemyCatalogReadRepository,
    catalog_admin_repository,
)
from app.infrastructure.adapters.secondary.persistence.audit_log_adapter import (
    SQLAlchemyAuditLogAdapter,
)
from app.infrastructure.adapters.secondary.persistence.database import (
    get_catalog_write_session,
    get_engine,
    get_session,
    get_sessionmaker,
)
from app.infrastructure.adapters.secondary.persistence.manual_booking_repository import (
    SqlAlchemyManualBookingStore,
)
from app.infrastructure.adapters.secondary.persistence.refresh_token_repository import (
    SQLAlchemyRefreshTokenRepository,
)
from app.infrastructure.adapters.secondary.persistence.repositories import (
    sqlalchemy_client_repository,
    sqlalchemy_event_repository,
    sqlalchemy_payment_repository,
    sqlalchemy_quote_repository,
)
from app.infrastructure.adapters.secondary.persistence.sqlalchemy_health_adapter import (
    SQLAlchemyHealthAdapter,
)
from app.infrastructure.adapters.secondary.persistence.user_repository import (
    SQLAlchemyUserRepository,
)
from app.infrastructure.adapters.secondary.storage.booking_pdf import contract_pdf
from app.infrastructure.adapters.secondary.storage.local_evidence_storage import (
    LocalEvidenceStorage,
)
from app.infrastructure.adapters.secondary.storage.postgres_booking_documents import (
    PostgresBookingDocuments,
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
def get_list_users_use_case() -> ListUsersUseCase:
    return ListUsersUseCase(get_user_repository())


@lru_cache
def get_create_user_use_case() -> CreateUserUseCase:
    return CreateUserUseCase(get_user_repository())


@lru_cache
def get_get_user_use_case() -> GetUserUseCase:
    return GetUserUseCase(get_user_repository())


@lru_cache
def get_update_user_use_case() -> UpdateUserUseCase:
    return UpdateUserUseCase(get_user_repository())


@lru_cache
def get_audit_log_port() -> IAuditLogPort:
    return SQLAlchemyAuditLogAdapter(get_sessionmaker())


@lru_cache
def get_audit_service() -> AuditService:
    return AuditService(get_audit_log_port())


@lru_cache
def get_list_audit_logs_use_case() -> ListAuditLogsUseCase:
    return ListAuditLogsUseCase(get_audit_log_port())


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


@lru_cache
def get_mobility_tariff() -> MobilityTariff:
    return build_mobility_tariff(get_settings())


@lru_cache
def get_financial_engine() -> FinancialEngine:
    return FinancialEngine(
        tariff=get_mobility_tariff(), advance_percent=get_settings().advance_percent
    )


@lru_cache
def get_route_estimator() -> IRouteEstimatorPort:
    # Adaptador real (Google u otro) se decide en el bloque del bot; el dominio no cambia.
    return FakeRouteEstimatorAdapter()


@lru_cache
def get_messaging_port() -> IMessagingPort:
    # Mientras no exista ChatwootMessagingAdapter, todos los entornos usan el adaptador falso.
    # Es un singleton del proceso cuyo historial en memoria crece sin límite; es temporal.
    return FakeMessagingAdapter(
        clock=get_clock_port(), log_messages=get_settings().app_env == "development"
    )


def get_quote_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IQuoteRepositoryPort:
    return sqlalchemy_quote_repository.SqlAlchemyQuoteRepository(session)


def get_client_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IClientRepositoryPort:
    return sqlalchemy_client_repository.SqlAlchemyClientRepository(session)


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
    return GetPaymentEvidenceUseCase(
        get_payment_repository(session), PostgresBookingDocuments(session, purpose="receipts")
    )


def get_availability_port(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IAvailabilityPort:
    settings = get_settings()
    return AvailabilityAdapter(
        repository=SqlAlchemyAvailabilityRepository(session),
        lock=RedisLockAdapter(get_redis_client()),
        concurrency_evaluator=ConcurrencyEvaluator(settings.simultaneous_shows_threshold),
        inventory_availability=InventoryAvailabilityService(),
        travel_interval_service=TravelIntervalService(settings.transit_rest_buffer_minutes),
    )


def get_catalog_read_port(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ICatalogReadPort:
    return SqlAlchemyCatalogReadRepository(session)


def get_catalog_admin_port(
    session: Annotated[AsyncSession, Depends(get_catalog_write_session, scope="function")],
) -> ICatalogAdminPort:
    return catalog_admin_repository.SqlAlchemyCatalogAdminRepository(session)


def get_crew_admin_port(
    session: Annotated[AsyncSession, Depends(get_catalog_write_session, scope="function")],
) -> ICrewAdminPort:
    return catalog_admin_repository.SqlAlchemyCrewAdminRepository(session)


def get_manage_catalog_use_case(
    session: Annotated[AsyncSession, Depends(get_catalog_write_session, scope="function")],
) -> ManageCatalogUseCase:
    return ManageCatalogUseCase(catalog_admin_repository.SqlAlchemyCatalogAdminRepository(session))


def get_manage_crews_use_case(
    session: Annotated[AsyncSession, Depends(get_catalog_write_session, scope="function")],
) -> ManageCrewsUseCase:
    return ManageCrewsUseCase(
        catalog_admin_repository.SqlAlchemyCrewAdminRepository(session), get_user_repository()
    )


def get_approve_overbooked_payment_use_case(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ApproveOverbookedPaymentUseCase:
    return ApproveOverbookedPaymentUseCase(
        get_payment_repository(session),
        get_audit_service(),
        sqlalchemy_event_repository.SqlAlchemyEventRepository(session),
    )


def clear_application_caches() -> None:
    """Suelta repositorios, servicios y casos de uso (sujetos al engine/loop activos)."""
    get_user_repository.cache_clear()
    get_refresh_token_repository.cache_clear()
    get_login_use_case.cache_clear()
    get_refresh_use_case.cache_clear()
    get_logout_use_case.cache_clear()
    get_list_users_use_case.cache_clear()
    get_create_user_use_case.cache_clear()
    get_get_user_use_case.cache_clear()
    get_update_user_use_case.cache_clear()
    get_audit_log_port.cache_clear()
    get_audit_service.cache_clear()
    get_list_audit_logs_use_case.cache_clear()
    get_evidence_storage.cache_clear()
    get_extension_evidence_storage.cache_clear()
    get_quote_schedule_read_port.cache_clear()
    get_crew_schedule_read_port.cache_clear()
    get_pre_show_payment_verification_port.cache_clear()
    get_clock_port.cache_clear()
    get_mobility_tariff.cache_clear()
    get_financial_engine.cache_clear()
    get_route_estimator.cache_clear()
    get_messaging_port.cache_clear()


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


def get_manual_booking_store(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IManualBookingStore:
    return SqlAlchemyManualBookingStore(session)


def get_booking_documents(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IBookingDocuments:
    return PostgresBookingDocuments(session)


def get_booking_receipts(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IBookingDocuments:
    return PostgresBookingDocuments(session, purpose="receipts")


def get_budget_documents(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IBookingDocuments:
    return PostgresBookingDocuments(session, purpose="budgets")


def get_prepare_budget_use_case(
    catalog: Annotated[ICatalogReadPort, Depends(get_catalog_read_port)],
    availability: Annotated[IAvailabilityPort, Depends(get_availability_port)],
) -> PrepareBudgetUseCase:
    return PrepareBudgetUseCase(catalog, availability, get_settings().advance_percent)


def get_confirm_manual_booking_use_case(
    store: Annotated[IManualBookingStore, Depends(get_manual_booking_store)],
    catalog: Annotated[ICatalogReadPort, Depends(get_catalog_read_port)],
    availability: Annotated[IAvailabilityPort, Depends(get_availability_port)],
    documents: Annotated[IBookingDocuments, Depends(get_booking_documents)],
) -> ConfirmManualBookingUseCase:
    return ConfirmManualBookingUseCase(store, catalog, availability, documents, contract_pdf)


def get_register_manual_booking_use_case(
    store: Annotated[IManualBookingStore, Depends(get_manual_booking_store)],
    budget: Annotated[PrepareBudgetUseCase, Depends(get_prepare_budget_use_case)],
    receipts: Annotated[IBookingDocuments, Depends(get_booking_receipts)],
) -> RegisterManualBookingUseCase:
    return RegisterManualBookingUseCase(store, budget, receipts)


def get_refund_manual_booking_use_case(
    store: Annotated[IManualBookingStore, Depends(get_manual_booking_store)],
) -> RefundManualBookingUseCase:
    return RefundManualBookingUseCase(store)
