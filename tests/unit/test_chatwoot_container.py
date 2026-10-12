"""Proveedores de Chatwoot en el contenedor: cliente HTTP, puerto de eventos y caso de uso."""

from collections.abc import Iterator

import httpx
import pytest

from app.application.use_cases.messaging.process_gateway_event import ProcessGatewayEvent
from app.core.config import get_settings
from app.infrastructure.adapters.secondary.external_services.chatwoot.chatwoot_client import (
    ChatwootClient,
)
from app.infrastructure.adapters.secondary.external_services.chatwoot.chatwoot_event_gateway import (  # noqa: E501
    ChatwootEventGateway,
)
from app.infrastructure.adapters.secondary.persistence.database import (
    get_engine,
    get_sessionmaker,
)
from app.infrastructure.adapters.secondary.persistence.repositories.sqlalchemy_outbox_repository import (  # noqa: E501
    SqlAlchemyOutboxTransaction,
)
from app.infrastructure.di import containers

_CHATWOOT_ENV = {
    "CHATWOOT_BASE_URL": "https://chatwoot.example.org/",
    "CHATWOOT_ACCOUNT_ID": "7",
    "CHATWOOT_INBOX_ID": "2",
    "CHATWOOT_BOT_TOKEN": "bot-token-value-1234",
    "CHATWOOT_AGENT_TOKEN": "agent-token-value-5678",
}


def _clear() -> None:
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()
    containers.get_chatwoot_http_client.cache_clear()
    containers.clear_application_caches()


@pytest.fixture(autouse=True)
def _fresh_caches(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("SECRET_KEY", "s" * 40)
    for name in _CHATWOOT_ENV:
        monkeypatch.delenv(name, raising=False)
    _clear()
    yield
    _clear()


@pytest.fixture
def chatwoot_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in _CHATWOOT_ENV.items():
        monkeypatch.setenv(name, value)


# --- Cliente HTTP -------------------------------------------------------------------------


@pytest.mark.usefixtures("chatwoot_env")
def test_the_http_client_targets_the_account_with_finite_timeouts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHATWOOT_TIMEOUT_SECONDS", "7")
    monkeypatch.setenv("CHATWOOT_CONNECT_TIMEOUT_SECONDS", "2")

    client = containers.get_chatwoot_http_client()

    assert str(client.base_url).rstrip("/") == "https://chatwoot.example.org/api/v1/accounts/7"
    timeout = client.timeout
    assert (timeout.connect, timeout.read, timeout.write, timeout.pool) == (2, 7, 7, 7)
    assert client.follow_redirects is False


@pytest.mark.usefixtures("chatwoot_env")
def test_the_http_client_is_a_cached_singleton() -> None:
    assert containers.get_chatwoot_http_client() is containers.get_chatwoot_http_client()


def test_the_http_client_cannot_be_built_without_configuration() -> None:
    with pytest.raises(RuntimeError, match="CHATWOOT_BASE_URL"):
        containers.get_chatwoot_http_client()


# --- Puerto de eventos --------------------------------------------------------------------


@pytest.mark.usefixtures("chatwoot_env")
def test_the_event_port_wraps_the_shared_client_when_chatwoot_is_configured() -> None:
    port = containers.get_gateway_event_port()

    assert isinstance(port, ChatwootEventGateway)
    assert isinstance(port._client, ChatwootClient)
    assert port._client._http is containers.get_chatwoot_http_client()
    assert containers.get_gateway_event_port() is port


async def test_the_event_port_has_no_client_when_chatwoot_is_not_configured() -> None:
    port = containers.get_gateway_event_port()

    assert isinstance(port, ChatwootEventGateway)
    assert port._client is None
    assert await port.get_delivery_status(57, "4821") is None
    assert containers.get_chatwoot_http_client.cache_info().currsize == 0


# --- Caso de uso --------------------------------------------------------------------------


def test_the_process_use_case_is_a_cached_singleton_with_its_own_transactions() -> None:
    use_case = containers.get_process_gateway_event_use_case()

    assert isinstance(use_case, ProcessGatewayEvent)
    assert containers.get_process_gateway_event_use_case() is use_case
    assert use_case._gateway is containers.get_gateway_event_port()
    assert isinstance(use_case._transaction, SqlAlchemyOutboxTransaction)


def test_clear_application_caches_resets_the_chatwoot_providers() -> None:
    port = containers.get_gateway_event_port()
    use_case = containers.get_process_gateway_event_use_case()

    containers.clear_application_caches()

    assert containers.get_gateway_event_port() is not port
    assert containers.get_process_gateway_event_use_case() is not use_case


# --- Cierre -------------------------------------------------------------------------------


@pytest.mark.usefixtures("chatwoot_env")
async def test_shutdown_closes_the_http_client_and_a_later_build_creates_a_fresh_one() -> None:
    first: httpx.AsyncClient = containers.get_chatwoot_http_client()
    assert first.is_closed is False

    await containers.shutdown_infrastructure()

    assert first.is_closed is True
    second = containers.get_chatwoot_http_client()
    assert second is not first
    assert second.is_closed is False
    await containers.shutdown_infrastructure()


async def test_shutdown_without_a_cached_client_does_not_build_one() -> None:
    await containers.shutdown_infrastructure()

    assert containers.get_chatwoot_http_client.cache_info().currsize == 0
