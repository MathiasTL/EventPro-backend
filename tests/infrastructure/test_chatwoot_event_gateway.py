"""ChatwootEventGateway: interpreta los webhooks y consulta el estado de entrega por la API."""

import copy
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from structlog.testing import capture_logs

from app.application.dtos.gateway_event_dto import (
    DeliveryNotice,
    DeliveryReport,
    UnhandledGatewayEvent,
)
from app.application.dtos.messaging_dto import MessageDirection
from app.domain.exceptions.messaging_exceptions import MessagingUnavailableError
from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.outbox import DeliveryStatus
from app.infrastructure.adapters.secondary.external_services.chatwoot.chatwoot_client import (
    TOKEN_HEADER,
    ChatwootClient,
)
from app.infrastructure.adapters.secondary.external_services.chatwoot.chatwoot_event_gateway import (  # noqa: E501
    ChatwootEventGateway,
)
from tests.chatwoot_fixture_support import load_fixture
from tests.infrastructure.chatwoot_support import AGENT_TOKEN, BASE_URL, BOT_TOKEN, ERROR_BODY

DELIVERED_AT = datetime(2026, 10, 19, 22, 6, 6, 836000, tzinfo=UTC)
READ_AT = datetime(2026, 10, 19, 22, 6, 7, 161000, tzinfo=UTC)
FAILED_AT = datetime(2026, 10, 19, 22, 34, 13, 132000, tzinfo=UTC)
REAL_ERROR = "(#131030) Recipient phone number not in allowed list"
MESSAGES_PATH = "/api/v1/accounts/1/conversations/57/messages"


def _body(name: str) -> dict[str, Any]:
    body = load_fixture(name)["body"]
    assert isinstance(body, dict)
    return copy.deepcopy(body)


def _embedded(body: dict[str, Any]) -> dict[str, Any]:
    """Mensaje que Chatwoot incrusta en `conversation.messages`: ahí viven estado y hora."""

    embedded: dict[str, Any] = body["conversation"]["messages"][0]
    return embedded


def _raw(body: Any) -> bytes:
    return json.dumps(body).encode()


def _parse(body: Any) -> Any:
    return ChatwootEventGateway(None).parse_event(_raw(body))


# --- parse_event: avisos de entrega -------------------------------------------------------


@pytest.mark.parametrize(
    ("fixture", "status", "updated_at"),
    [
        ("message_updated_delivered", DeliveryStatus.DELIVERED, DELIVERED_AT),
        ("message_updated_read", DeliveryStatus.READ, READ_AT),
    ],
)
def test_a_delivered_or_read_update_becomes_a_delivery_notice(
    fixture: str, status: DeliveryStatus, updated_at: datetime
) -> None:
    event = _parse(_body(fixture))

    assert event == DeliveryNotice(
        external_message_id="6",
        conversation_id=1,
        status=status,
        error=None,
        updated_at=updated_at,
        status_in_payload=True,
    )


def test_a_failed_update_carries_the_external_error_text() -> None:
    event = _parse(_body("message_updated_failed"))

    assert event == DeliveryNotice(
        external_message_id="7",
        conversation_id=2,
        status=DeliveryStatus.FAILED,
        error=REAL_ERROR,
        updated_at=FAILED_AT,
        status_in_payload=True,
    )


def test_a_sent_update_has_a_status_in_the_payload_that_is_not_recordable() -> None:
    event = _parse(_body("message_updated_sent"))

    assert isinstance(event, DeliveryNotice)
    assert event.status is None
    assert event.status_in_payload is True


def test_the_message_status_is_not_read_from_the_top_level_of_the_body() -> None:
    # Capturas reales: el cuerpo no trae `status`; vive en `conversation.messages[0].status`.
    body = _body("message_updated_sent")
    assert "status" not in body
    body["status"] = "read"

    event = _parse(body)

    assert isinstance(event, DeliveryNotice)
    assert event.status is None


def test_an_update_without_status_asks_for_a_lookup_and_keeps_the_error_text() -> None:
    body = _body("message_updated_failed")
    del _embedded(body)["status"]

    event = _parse(body)

    assert isinstance(event, DeliveryNotice)
    assert (event.status, event.status_in_payload) == (None, False)
    assert event.error == REAL_ERROR


def test_an_update_whose_embedded_message_is_another_one_is_not_trusted() -> None:
    body = _body("message_updated_delivered")
    _embedded(body)["id"] = 99

    event = _parse(body)

    assert isinstance(event, DeliveryNotice)
    assert (event.status, event.status_in_payload, event.updated_at) == (None, False, None)


def test_the_embedded_message_is_found_by_id_among_several() -> None:
    body = _body("message_updated_delivered")
    body["conversation"]["messages"].insert(0, {"id": 99, "status": "read"})

    event = _parse(body)

    assert isinstance(event, DeliveryNotice)
    assert event.status is DeliveryStatus.DELIVERED


def test_the_error_text_falls_back_to_the_embedded_message() -> None:
    body = _body("message_updated_failed")
    del body["content_attributes"]

    event = _parse(body)

    assert isinstance(event, DeliveryNotice)
    assert event.error == REAL_ERROR


def test_an_update_without_update_time_leaves_it_empty() -> None:
    body = _body("message_updated_delivered")
    del _embedded(body)["updated_at"]

    assert _parse(body).updated_at is None


def test_an_update_time_that_cannot_be_read_is_left_empty() -> None:
    body = _body("message_updated_delivered")
    _embedded(body)["updated_at"] = "ayer por la tarde"

    assert _parse(body).updated_at is None


def test_an_update_time_with_an_offset_is_converted_to_utc() -> None:
    body = _body("message_updated_delivered")
    _embedded(body)["updated_at"] = "2026-10-19T17:06:06.836-05:00"

    assert _parse(body).updated_at == DELIVERED_AT


def test_an_update_without_conversation_has_no_conversation_id() -> None:
    body = _body("message_updated_delivered")
    del body["conversation"]

    event = _parse(body)

    assert event.conversation_id is None
    assert (event.status, event.status_in_payload) == (None, False)


@pytest.mark.parametrize("message_type", ["outgoing", 1])
def test_both_encodings_of_an_outgoing_message_are_delivery_notices(
    message_type: str | int,
) -> None:
    body = _body("message_updated_delivered")
    body["message_type"] = message_type

    assert isinstance(_parse(body), DeliveryNotice)


@pytest.mark.parametrize("message_type", ["incoming", 0])
def test_an_update_of_an_incoming_message_is_not_a_delivery_notice(
    message_type: str | int,
) -> None:
    body = _body("message_updated_delivered")
    body["message_type"] = message_type

    assert _parse(body) == UnhandledGatewayEvent(
        kind="message_updated",
        direction=MessageDirection.INCOMING,
        conversation_id=1,
        external_message_id="6",
    )


def test_an_update_of_a_private_note_is_not_a_delivery_notice() -> None:
    body = _body("message_updated_delivered")
    body["private"] = True

    assert _parse(body) == UnhandledGatewayEvent(
        kind="message_updated",
        direction=MessageDirection.OUTGOING,
        conversation_id=1,
        external_message_id="6",
    )


# --- parse_event: el resto de los eventos -------------------------------------------------


def test_an_incoming_created_message_is_unhandled() -> None:
    assert _parse(_body("message_created_incoming")) == UnhandledGatewayEvent(
        kind="message_created",
        direction=MessageDirection.INCOMING,
        conversation_id=1,
        external_message_id="5",
    )


def test_an_outgoing_created_message_is_unhandled() -> None:
    assert _parse(_body("message_created_outgoing")) == UnhandledGatewayEvent(
        kind="message_created",
        direction=MessageDirection.OUTGOING,
        conversation_id=1,
        external_message_id="6",
    )


def test_a_conversation_event_carries_its_conversation_id() -> None:
    event = _parse({"event": "conversation_status_changed", "id": 57, "status": "open"})

    assert event == UnhandledGatewayEvent(
        kind="conversation_status_changed",
        direction=None,
        conversation_id=57,
        external_message_id=None,
    )


@pytest.mark.parametrize("body", [{"id": 4821}, {"event": 7}, {"event": ""}])
def test_a_missing_or_invalid_event_name_is_an_unknown_event(body: dict[str, Any]) -> None:
    assert _parse(body) == UnhandledGatewayEvent(
        kind="unknown", direction=None, conversation_id=None, external_message_id=None
    )


# --- parse_event: cuerpos que no se reconocen ---------------------------------------------


@pytest.mark.parametrize(
    "raw_body",
    [b"", b"no es json", b"\xff\xfe", b"[1, 2]", b'"texto"', b"null"],
    ids=["empty", "text", "bad-utf8", "array", "string", "null"],
)
def test_a_body_that_is_not_a_json_object_is_rejected(raw_body: bytes) -> None:
    with pytest.raises(ValidationError):
        ChatwootEventGateway(None).parse_event(raw_body)


@pytest.mark.parametrize("message_id", [None, "4821", True, 4821.5])
def test_a_delivery_notice_needs_an_integer_message_id(message_id: object) -> None:
    body = _body("message_updated_delivered")
    body["id"] = message_id

    with pytest.raises(ValidationError):
        _parse(body)


def test_a_delivery_notice_without_message_id_is_rejected() -> None:
    body = _body("message_updated_delivered")
    del body["id"]

    with pytest.raises(ValidationError):
        _parse(body)


def test_parsing_does_not_log_anything() -> None:
    with capture_logs() as logs:
        _parse(_body("message_created_incoming"))
        _parse(_body("message_updated_failed"))

    assert logs == []


# --- get_delivery_status ------------------------------------------------------------------


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> ChatwootClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=BASE_URL)
    return ChatwootClient(http, bot_token=BOT_TOKEN, agent_token=AGENT_TOKEN)


def _item(message_id: int, **fields: Any) -> dict[str, Any]:
    return {
        "id": message_id,
        "conversation_id": 57,
        "message_type": 1,
        "private": False,
        "content": "Codigo 123456 para 51999111222",
        "created_at": 1_791_813_600,
        "attachments": [],
        **fields,
    }


class _MessageApi:
    """Responde al listado de mensajes con las páginas que se le indiquen."""

    def __init__(self, items: list[dict[str, Any]]) -> None:
        self.items = items
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(200, json={"payload": self.items})


async def test_the_lookup_reads_the_message_before_the_next_id_with_the_agent_token() -> None:
    api = _MessageApi([_item(4820), _item(4821, status="delivered")])

    report = await ChatwootEventGateway(_client(api)).get_delivery_status(57, "4821")

    assert report == DeliveryReport(status=DeliveryStatus.DELIVERED, error=None)
    (request,) = api.requests
    assert request.method == "GET"
    assert request.url.path == MESSAGES_PATH
    assert request.url.params["before"] == "4822"
    assert request.headers[TOKEN_HEADER] == AGENT_TOKEN


@pytest.mark.parametrize(
    ("status", "expected"),
    [("delivered", DeliveryStatus.DELIVERED), ("read", DeliveryStatus.READ)],
)
async def test_the_lookup_maps_delivered_and_read(status: str, expected: DeliveryStatus) -> None:
    api = _MessageApi([_item(4821, status=status)])

    report = await ChatwootEventGateway(_client(api)).get_delivery_status(57, "4821")

    assert report == DeliveryReport(status=expected, error=None)


async def test_the_lookup_returns_the_external_error_of_a_failed_message() -> None:
    api = _MessageApi(
        [
            _item(
                4821,
                status="failed",
                content_attributes={"external_error": "message_outside_messaging_window"},
            )
        ]
    )

    report = await ChatwootEventGateway(_client(api)).get_delivery_status(57, "4821")

    assert report == DeliveryReport(
        status=DeliveryStatus.FAILED, error="message_outside_messaging_window"
    )


@pytest.mark.parametrize("fields", [{"status": "sent"}, {"status": "weird"}, {}])
async def test_the_lookup_reports_no_status_when_the_message_is_not_delivered_yet(
    fields: dict[str, Any],
) -> None:
    api = _MessageApi([_item(4821, **fields)])

    report = await ChatwootEventGateway(_client(api)).get_delivery_status(57, "4821")

    assert report == DeliveryReport(status=None, error=None)


async def test_the_lookup_picks_the_item_with_the_matching_id() -> None:
    api = _MessageApi(
        [_item(4819, status="read"), _item(4821, status="delivered"), _item(4820, status="read")]
    )

    report = await ChatwootEventGateway(_client(api)).get_delivery_status(57, "4821")

    assert report is not None and report.status is DeliveryStatus.DELIVERED


async def test_the_lookup_returns_none_when_the_message_is_not_in_the_page() -> None:
    api = _MessageApi([_item(4819, status="read"), _item(4820, status="read")])

    assert await ChatwootEventGateway(_client(api)).get_delivery_status(57, "4821") is None


async def test_the_lookup_returns_none_when_the_conversation_does_not_exist() -> None:
    gateway = ChatwootEventGateway(_client(lambda request: httpx.Response(404)))

    assert await gateway.get_delivery_status(57, "4821") is None


async def test_the_lookup_returns_none_without_a_configured_client() -> None:
    assert await ChatwootEventGateway(None).get_delivery_status(57, "4821") is None


async def test_the_lookup_returns_none_for_an_external_id_that_is_not_a_number() -> None:
    api = _MessageApi([_item(4821, status="read")])

    assert await ChatwootEventGateway(_client(api)).get_delivery_status(57, "wamid.X") is None
    assert api.requests == []


@pytest.mark.parametrize(
    "handler",
    [
        lambda request: httpx.Response(503, text=ERROR_BODY),
        lambda request: httpx.Response(401, text=ERROR_BODY),
        lambda request: (_ for _ in ()).throw(httpx.ConnectError("caído", request=request)),
        lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("lento", request=request)),
    ],
    ids=["503", "401", "connect-error", "timeout"],
)
async def test_a_gateway_failure_propagates_as_messaging_unavailable(
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    with pytest.raises(MessagingUnavailableError):
        await ChatwootEventGateway(_client(handler)).get_delivery_status(57, "4821")


async def test_a_response_without_a_message_list_is_an_unexpected_response() -> None:
    gateway = ChatwootEventGateway(_client(lambda request: httpx.Response(200, json={"x": 1})))

    with pytest.raises(MessagingUnavailableError):
        await gateway.get_delivery_status(57, "4821")


async def test_the_lookup_logs_neither_content_nor_phone_numbers() -> None:
    api = _MessageApi([_item(4821, status="failed", content_attributes={"external_error": "x1"})])

    with capture_logs() as logs:
        await ChatwootEventGateway(_client(api)).get_delivery_status(57, "4821")
        failing = ChatwootEventGateway(
            _client(lambda request: httpx.Response(503, text=ERROR_BODY))
        )
        with pytest.raises(MessagingUnavailableError):
            await failing.get_delivery_status(57, "4821")

    dump = json.dumps(logs, default=str)
    assert "123456" not in dump
    assert "51999111222" not in dump
    assert AGENT_TOKEN not in dump and BOT_TOKEN not in dump
