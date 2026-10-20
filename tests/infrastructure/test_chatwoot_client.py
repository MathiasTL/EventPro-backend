"""Cliente HTTP de Chatwoot: autenticación por operación y clasificación de errores."""

from collections.abc import Callable
from typing import Any

import httpx
import pytest
from structlog.testing import capture_logs

from app.domain.exceptions.messaging_exceptions import MessagingUnavailableError
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError
from app.infrastructure.adapters.secondary.external_services.chatwoot.chatwoot_client import (
    ChatwootClient,
    ChatwootToken,
    build_chatwoot_http_client,
)

_BOT_TOKEN = "bot-token-value-1234"
_AGENT_TOKEN = "agent-token-value-5678"
_PHONE_DIGITS = "51999111222"
_BODY_TEXT = "Codigo 123456"
_BASE_URL = "https://chatwoot.example.org/api/v1/accounts/1"

Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler) -> ChatwootClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=_BASE_URL)
    return ChatwootClient(http, bot_token=_BOT_TOKEN, agent_token=_AGENT_TOKEN)


def _status_handler(status: int) -> Handler:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=f"cuerpo con {_BODY_TEXT} y {_PHONE_DIGITS}")

    return handler


def _raising_handler(error: Exception) -> Handler:
    def handler(_: httpx.Request) -> httpx.Response:
        raise error

    return handler


async def _call(client: ChatwootClient, **kwargs: Any) -> Any:
    return await client.request(
        "GET",
        "/contacts/search",
        token=kwargs.pop("token", ChatwootToken.AGENT),
        operation="search_contact",
        params={"q": _PHONE_DIGITS},
        **kwargs,
    )


@pytest.mark.parametrize(
    ("token", "expected"),
    [(ChatwootToken.BOT, _BOT_TOKEN), (ChatwootToken.AGENT, _AGENT_TOKEN)],
)
async def test_each_call_uses_the_header_of_its_token(token: ChatwootToken, expected: str) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"payload": []})

    assert await _call(_client(handler), token=token) == {"payload": []}
    assert seen[0].headers["api_access_token"] == expected
    assert "authorization" not in seen[0].headers


async def test_request_carries_method_path_query_and_json_body() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"id": 7})

    client = _client(handler)
    result = await client.request(
        "POST",
        "/conversations",
        token=ChatwootToken.AGENT,
        operation="create_conversation",
        json={"inbox_id": 2, "contact_id": 9},
    )
    assert result == {"id": 7}
    assert seen[0].method == "POST"
    assert seen[0].url.path == "/api/v1/accounts/1/conversations"
    assert seen[0].read() == b'{"inbox_id":2,"contact_id":9}'


async def test_multipart_upload_sends_fields_and_file_part() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"id": 1})

    await _client(handler).request(
        "POST",
        "/conversations/5/messages",
        token=ChatwootToken.BOT,
        operation="send_message",
        data={"message_type": "outgoing"},
        files=[("attachments[]", ("cotizacion.pdf", b"%PDF-1", "application/pdf"))],
    )
    body = seen[0].read()
    assert seen[0].headers["content-type"].startswith("multipart/form-data")
    assert b'name="attachments[]"; filename="cotizacion.pdf"' in body
    assert b"Content-Type: application/pdf" in body
    assert b'name="message_type"' in body


@pytest.mark.parametrize(
    "error",
    [
        httpx.ReadTimeout("lento"),
        httpx.ConnectTimeout("lento"),
        httpx.ConnectError("sin ruta"),
        httpx.RemoteProtocolError("corte"),
    ],
)
async def test_transport_failures_are_unavailable(error: Exception) -> None:
    with pytest.raises(MessagingUnavailableError):
        await _call(_client(_raising_handler(error)))


@pytest.mark.parametrize("status", [500, 502, 503, 429, 401, 403, 422, 400, 409, 404])
async def test_error_statuses_are_unavailable(status: int) -> None:
    with pytest.raises(MessagingUnavailableError) as error:
        await _call(_client(_status_handler(status)))
    assert str(status) in str(error.value)


async def test_404_is_missing_resource_only_when_requested() -> None:
    client = _client(_status_handler(404))
    with pytest.raises(ResourceNotFoundError):
        await _call(client, not_found_is_missing=True)
    with pytest.raises(MessagingUnavailableError):
        await _call(client)


async def test_not_found_flag_does_not_change_other_statuses() -> None:
    with pytest.raises(MessagingUnavailableError):
        await _call(_client(_status_handler(500)), not_found_is_missing=True)


@pytest.mark.parametrize("body", [b"<html>502</html>", b"", b"[1, 2"])
async def test_non_json_body_is_an_unexpected_response(body: bytes) -> None:
    client = _client(lambda _: httpx.Response(200, content=body))
    with capture_logs() as logs, pytest.raises(MessagingUnavailableError):
        await _call(client)
    event = next(entry for entry in logs if entry["event"] == "chatwoot_unexpected_response")
    assert event["operation"] == "search_contact"


async def test_missing_required_key_is_an_unexpected_response() -> None:
    client = _client(lambda _: httpx.Response(200, json={"other": 1}))
    with capture_logs() as logs, pytest.raises(MessagingUnavailableError):
        await _call(client, required_keys=("payload",))
    event = next(entry for entry in logs if entry["event"] == "chatwoot_unexpected_response")
    assert event["key"] == "payload"


async def test_required_keys_present_returns_the_body() -> None:
    client = _client(lambda _: httpx.Response(200, json={"payload": [1]}))
    assert await _call(client, required_keys=("payload",)) == {"payload": [1]}


@pytest.mark.parametrize("status", [401, 403])
async def test_rejected_credentials_are_logged(status: int) -> None:
    with capture_logs() as logs, pytest.raises(MessagingUnavailableError):
        await _call(_client(_status_handler(status)))
    event = next(entry for entry in logs if entry["event"] == "chatwoot_auth_rejected")
    assert event["status"] == status
    assert event["log_level"] == "error"


@pytest.mark.parametrize(
    "handler",
    [
        _status_handler(500),
        _status_handler(401),
        _status_handler(422),
        _raising_handler(httpx.ConnectError(f"fallo {_BASE_URL} {_BOT_TOKEN} {_PHONE_DIGITS}")),
        _raising_handler(httpx.ReadTimeout(f"lento {_AGENT_TOKEN}")),
        lambda _: httpx.Response(200, text=f"no es json {_BODY_TEXT} {_PHONE_DIGITS}"),
    ],
)
async def test_errors_and_logs_leak_no_secret_body_phone_or_query(handler: Handler) -> None:
    with capture_logs() as logs, pytest.raises(MessagingUnavailableError) as error:
        await _call(_client(handler))
    rendered = f"{error.value} {logs}"
    for forbidden in (
        _BOT_TOKEN,
        _AGENT_TOKEN,
        _BODY_TEXT,
        _PHONE_DIGITS,
        "?q=",
        "chatwoot.example",
    ):
        assert forbidden not in rendered
    assert "search_contact" in str(error.value)


async def test_shared_http_client_has_finite_timeouts_and_no_redirects() -> None:
    http = build_chatwoot_http_client(
        base_url="https://chatwoot.example.org",
        account_id=1,
        timeout_seconds=10.0,
        connect_timeout_seconds=3.0,
    )
    try:
        assert str(http.base_url).rstrip("/") == "https://chatwoot.example.org/api/v1/accounts/1"
        timeout = http.timeout
        assert (timeout.connect, timeout.read, timeout.write, timeout.pool) == (
            3.0,
            10.0,
            10.0,
            10.0,
        )
        assert http.follow_redirects is False
        assert "api_access_token" not in http.headers
        assert "authorization" not in http.headers
    finally:
        await http.aclose()
