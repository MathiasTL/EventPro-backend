from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest

from app.application.use_cases.messaging.dispatch_due_messages import DispatchDueMessages
from app.application.use_cases.messaging.enqueue_message import EnqueueMessage
from app.core.config import get_settings
from app.infrastructure.adapters.secondary.persistence.database import (
    get_engine,
    get_sessionmaker,
)
from app.infrastructure.adapters.secondary.persistence.repositories.sqlalchemy_outbox_repository import (  # noqa: E501
    SqlAlchemyOutboxRepository,
)
from app.infrastructure.adapters.secondary.storage.document_source_adapter import (
    StorageDocumentSource,
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


def test_enqueue_use_case_is_built_on_the_callers_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OUTBOX_MAX_ATTEMPTS", "4")
    session = MagicMock()

    use_case = containers.get_enqueue_message_use_case(session)

    assert isinstance(use_case, EnqueueMessage)
    assert use_case._max_attempts == 4
    repository = use_case._repository
    assert isinstance(repository, SqlAlchemyOutboxRepository)
    assert repository._session is session


def test_dispatch_use_case_is_a_cached_singleton_with_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OUTBOX_BATCH_SIZE", "7")
    monkeypatch.setenv("OUTBOX_LEASE_SECONDS", "90")

    use_case = containers.get_dispatch_due_messages_use_case()

    assert isinstance(use_case, DispatchDueMessages)
    assert containers.get_dispatch_due_messages_use_case() is use_case
    assert use_case._batch_size == 7
    assert use_case._lease.total_seconds() == 90
    assert use_case._messaging is containers.get_messaging_port()


def test_document_source_is_the_storage_adapter() -> None:
    assert isinstance(containers.get_document_source_port(), StorageDocumentSource)
    assert containers.get_document_source_port() is containers.get_document_source_port()


def test_clear_application_caches_resets_the_outbox_providers() -> None:
    first = containers.get_dispatch_due_messages_use_case()
    containers.clear_application_caches()
    assert containers.get_dispatch_due_messages_use_case() is not first
