"""Proveedores de Chatwoot en el contenedor: cliente HTTP, puerto de eventos y caso de uso."""

from collections.abc import Iterator

import httpx
import pytest
from arq.connections import ArqRedis

from app.application.use_cases.messaging.process_gateway_event import ProcessGatewayEvent
from app.application.use_cases.messaging.receive_gateway_event import ReceiveGatewayEvent
from app.core.config import get_settings
from app.infrastructure.adapters.secondary.cache.redis_event_dedup_adapter import (
    RedisEventDedupAdapter,
)
from app.infrastructure.adapters.secondary.external_services.chatwoot.chatwoot_client import (
    ChatwootClient,
)
from app.infrastructure.adapters.secondary.external_services.chatwoot.chatwoot_event_gateway import (  # noqa: E501
    ChatwootEventGateway,
)
from app.infrastructure.adapters.secondary.external_services.chatwoot.chatwoot_messaging_adapter import (  # noqa: E501
    ChatwootMessagingAdapter,
)
from app.infrastructure.adapters.secondary.external_services.fake_messaging_adapter import (
    FakeMessagingAdapter,
)
from app.infrastructure.adapters.secondary.persistence.database import (
    get_engine,
    get_sessionmaker,
)
from app.infrastructure.adapters.secondary.persistence.repositories.sqlalchemy_outbox_repository import (  # noqa: E501
    SqlAlchemyOutboxTransaction,
)
from app.infrastructure.adapters.secondary.queue.arq_gateway_event_queue import (
    ArqGatewayEventQueue,
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
    containers.get_redis_client.cache_clear()
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


# --- Puerto de mensajería -----------------------------------------------------------------


def test_the_messaging_port_is_the_fake_adapter_without_a_base_url() -> None:
    port = containers.get_messaging_port()

    assert isinstance(port, FakeMessagingAdapter)
    assert containers.get_messaging_port() is port
    assert containers.get_chatwoot_http_client.cache_info().currsize == 0


@pytest.mark.usefixtures("chatwoot_env")
def test_the_messaging_port_is_the_chatwoot_adapter_when_the_base_url_is_set() -> None:
    port = containers.get_messaging_port()

    assert isinstance(port, ChatwootMessagingAdapter)
    assert containers.get_messaging_port() is port


@pytest.mark.usefixtures("chatwoot_env")
def test_the_messaging_port_shares_the_cached_http_client_and_the_inbox() -> None:
    port = containers.get_messaging_port()

    assert isinstance(port, ChatwootMessagingAdapter)
    assert port._client._http is containers.get_chatwoot_http_client()
    assert port._inbox_id == 2


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


# --- Recepción del webhook: pool de arq, deduplicación y cola --------------------------------


def test_the_arq_pool_is_built_from_the_redis_settings_without_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REDIS_HOST", "redis-de-prueba")
    monkeypatch.setenv("REDIS_PORT", "6390")
    monkeypatch.setenv("REDIS_DB", "3")
    monkeypatch.setenv("REDIS_PASSWORD", "clave-de-prueba")

    pool = containers.get_arq_pool()

    assert isinstance(pool, ArqRedis)
    kwargs = pool.connection_pool.connection_kwargs
    assert (kwargs["host"], kwargs["port"], kwargs["db"]) == ("redis-de-prueba", 6390, 3)
    assert kwargs["password"] == "clave-de-prueba"
    assert containers.get_arq_pool() is pool


def test_the_arq_pool_is_not_cached_across_a_cache_clear() -> None:
    pool = containers.get_arq_pool()

    containers.clear_application_caches()

    assert containers.get_arq_pool() is not pool


async def test_shutdown_closes_the_arq_pool_and_a_later_build_creates_a_fresh_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = containers.get_arq_pool()
    closed: list[bool] = []
    real_close = pool.aclose

    async def spy(*args: object, **kwargs: object) -> None:
        closed.append(True)
        await real_close(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(pool, "aclose", spy)

    await containers.shutdown_infrastructure()

    assert closed == [True]
    assert containers.get_arq_pool() is not pool


async def test_shutdown_without_a_cached_pool_does_not_build_one() -> None:
    await containers.shutdown_infrastructure()

    assert containers.get_arq_pool.cache_info().currsize == 0


def test_the_dedup_port_wraps_the_shared_redis_client() -> None:
    port = containers.get_event_dedup_port()

    assert isinstance(port, RedisEventDedupAdapter)
    assert port._client is containers.get_redis_client()
    assert containers.get_event_dedup_port() is port


def test_the_queue_port_wraps_the_arq_pool() -> None:
    port = containers.get_gateway_event_queue_port()

    assert isinstance(port, ArqGatewayEventQueue)
    assert port._pool is containers.get_arq_pool()
    assert containers.get_gateway_event_queue_port() is port


def test_the_receive_use_case_is_a_cached_singleton_over_the_dedup_and_queue_ports() -> None:
    use_case = containers.get_receive_gateway_event_use_case()

    assert isinstance(use_case, ReceiveGatewayEvent)
    assert containers.get_receive_gateway_event_use_case() is use_case
    assert use_case._dedup is containers.get_event_dedup_port()
    assert use_case._queue is containers.get_gateway_event_queue_port()


def test_clear_application_caches_resets_the_reception_providers() -> None:
    dedup = containers.get_event_dedup_port()
    queue = containers.get_gateway_event_queue_port()
    use_case = containers.get_receive_gateway_event_use_case()

    containers.clear_application_caches()

    assert containers.get_event_dedup_port() is not dedup
    assert containers.get_gateway_event_queue_port() is not queue
    assert containers.get_receive_gateway_event_use_case() is not use_case


async def test_the_application_lifespan_still_ends_in_shutdown_infrastructure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.main as main_module

    calls: list[str] = []

    async def fake_shutdown() -> None:
        calls.append("shutdown")

    monkeypatch.setattr(main_module, "shutdown_infrastructure", fake_shutdown)
    # configure_logging cambia la configuración global de structlog y contaminaría otras pruebas.
    monkeypatch.setattr(main_module, "configure_logging", lambda level: None)

    async with main_module.lifespan(main_module.app):
        assert calls == []

    assert calls == ["shutdown"]
