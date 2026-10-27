"""Proveedores del bot en ``containers.py``: unidad de trabajo, sesión y caso de uso."""

from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest

from app.application.use_cases.bot.bot_handoff import BotHandoffRecorder
from app.application.use_cases.bot.handle_incoming_message import HandleIncomingMessage
from app.application.use_cases.messaging.enqueue_message import EnqueueMessage
from app.application.use_cases.messaging.process_gateway_event import ProcessGatewayEvent
from app.application.use_cases.quote.create_quote import CreateQuoteUseCase
from app.application.use_cases.quote.pay_advance import PayAdvanceUseCase
from app.core.config import get_settings
from app.infrastructure.adapters.secondary.cache.redis_conversation_session_adapter import (
    RedisConversationSessionAdapter,
)
from app.infrastructure.adapters.secondary.cache.redis_lock_adapter import RedisLockAdapter
from app.infrastructure.adapters.secondary.events.redis_conversation_event_publisher import (
    RedisConversationEventPublisher,
)
from app.infrastructure.adapters.secondary.persistence import SqlAlchemyCatalogReadRepository
from app.infrastructure.adapters.secondary.persistence.database import (
    get_engine,
    get_sessionmaker,
)
from app.infrastructure.adapters.secondary.persistence.repositories.sqlalchemy_conversation_link_repository import (  # noqa: E501
    SqlAlchemyConversationLinkRepository,
)
from app.infrastructure.adapters.secondary.persistence.repositories.sqlalchemy_outbox_repository import (  # noqa: E501
    SqlAlchemyOutboxRepository,
)
from app.infrastructure.adapters.secondary.persistence.sqlalchemy_bot_unit_of_work import (
    SqlAlchemyBotUnitOfWork,
)
from app.infrastructure.adapters.secondary.persistence.sqlalchemy_inbox_event_unit_of_work import (
    SqlAlchemyInboxEventUnitOfWork,
)
from app.infrastructure.di import containers


@pytest.fixture(autouse=True)
def _fresh_caches(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("SECRET_KEY", "s" * 40)
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()
    containers.clear_application_caches()
    yield
    containers.clear_application_caches()
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()


def test_a_bot_transaction_shares_one_session_between_enqueue_and_catalog() -> None:
    session = MagicMock()

    transaction = containers.build_bot_transaction(session)

    assert isinstance(transaction.enqueue_message, EnqueueMessage)
    repository = transaction.enqueue_message._repository
    assert isinstance(repository, SqlAlchemyOutboxRepository)
    assert repository._session is session
    assert isinstance(transaction.catalog, SqlAlchemyCatalogReadRepository)
    assert transaction.catalog._session is session
    # El vínculo de la cotización comparte la sesión: se confirma con ella (spec 09, 6.2).
    assert isinstance(transaction.conversation_links, SqlAlchemyConversationLinkRepository)
    assert transaction.conversation_links._session is session


def test_the_quote_ports_come_from_the_shared_providers_so_swapping_them_is_one_line() -> None:
    session = MagicMock()
    transaction = containers.build_bot_transaction(session)

    assert transaction.create_quote._quotes._session is session
    assert isinstance(transaction.create_quote, CreateQuoteUseCase)
    assert isinstance(transaction.pay_advance, PayAdvanceUseCase)
    assert transaction.pay_advance._quotes._session is session


def test_the_bot_use_case_is_a_cached_singleton_wired_to_redis_and_the_unit_of_work() -> None:
    use_case = containers.get_handle_incoming_message_use_case()

    assert isinstance(use_case, HandleIncomingMessage)
    assert containers.get_handle_incoming_message_use_case() is use_case
    assert isinstance(use_case._unit_of_work, SqlAlchemyBotUnitOfWork)
    assert isinstance(use_case._sessions, RedisConversationSessionAdapter)
    assert isinstance(use_case._lock, RedisLockAdapter)
    assert isinstance(use_case._handoffs, BotHandoffRecorder)


def test_the_gateway_event_use_case_hands_client_messages_to_the_bot() -> None:
    use_case = containers.get_process_gateway_event_use_case()

    assert isinstance(use_case, ProcessGatewayEvent)
    assert use_case._incoming_handler is containers.get_handle_incoming_message_use_case()
    assert isinstance(use_case._inbox, SqlAlchemyInboxEventUnitOfWork)
    # B4: el worker publica por Redis (el registrador queda para pruebas y desarrollo).
    assert isinstance(use_case._publisher, RedisConversationEventPublisher)
