"""Adaptador de mensajería de Chatwoot: envíos, estado de conversación y lectura."""

import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from structlog.testing import capture_logs

from app.application.dtos.messaging_dto import (
    ConversationStatus,
    ListRow,
    ListSection,
    MessageDirection,
    MessageReceipt,
)
from app.application.ports.output.messaging_port import IMessagingPort
from app.domain.exceptions.messaging_exceptions import (
    MessagingUnavailableError,
    ServiceWindowClosedError,
)
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError
from app.domain.value_objects.phone_number import PhoneNumber
from app.infrastructure.adapters.secondary.external_services.chatwoot.chatwoot_messaging_adapter import (  # noqa: E501
    ChatwootMessagingAdapter,
)
from tests.chatwoot_fixture_support import load_fixture
from tests.infrastructure.chatwoot_support import (
    ACCOUNT_ID,
    AGENT_TOKEN,
    BASE_URL,
    BOT_TOKEN,
    FIRST_EPOCH,
    INBOX_ID,
    WAMID,
    FakeChatwootServer,
    parse_multipart,
)
from tests.infrastructure.messaging_port_contract import MessagingPortContract

PHONE = PhoneNumber("+51999111222")
OTHER_PHONE = PhoneNumber("+51999333444")
SUPERSTRING_PHONE = PhoneNumber("+519991112223")
SECTIONS = (ListSection("Paquetes", (ListRow("pkg-1", "Show infantil", "Duración 2 h"),)),)

Send = Callable[[ChatwootMessagingAdapter, PhoneNumber], Awaitable[MessageReceipt]]


async def _send_text(adapter: ChatwootMessagingAdapter, to: PhoneNumber) -> MessageReceipt:
    return await adapter.send_text(to, "Hola")


async def _send_list(adapter: ChatwootMessagingAdapter, to: PhoneNumber) -> MessageReceipt:
    return await adapter.send_interactive_list(to, "Elige", SECTIONS)


async def _send_attachment(adapter: ChatwootMessagingAdapter, to: PhoneNumber) -> MessageReceipt:
    return await adapter.send_attachment(to, b"%PDF", "cotizacion.pdf", "application/pdf", None)


FREE_FORM_SENDS = pytest.mark.parametrize(
    "send", [_send_text, _send_list, _send_attachment], ids=["text", "list", "attachment"]
)


@pytest.fixture
def server() -> FakeChatwootServer:
    return FakeChatwootServer()


@pytest.fixture
def adapter(server: FakeChatwootServer) -> ChatwootMessagingAdapter:
    return ChatwootMessagingAdapter(
        server.client(),
        inbox_id=INBOX_ID,
        template_language="es",
        template_category="UTILITY",
    )


def _request_body(server: FakeChatwootServer, method: str, path: str) -> dict[str, Any]:
    matching = [r for r in server.requests if r.method == method and _relative(r.url.path) == path]
    assert len(matching) == 1
    body = json.loads(matching[0].content)
    assert isinstance(body, dict)
    return body


def _relative(path: str) -> str:
    return path.removeprefix(f"/api/v1/accounts/{ACCOUNT_ID}")


def _message_posts(server: FakeChatwootServer) -> list[tuple[str, str, str]]:
    return [entry for entry in server.log if entry[0] == "POST" and entry[1].endswith("/messages")]


# ---------------------------------------------------------------------------
# Contacto: búsqueda por subcadena y coincidencia exacta
# ---------------------------------------------------------------------------


async def test_existing_contact_with_exact_phone_is_reused(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    contact_id = server.add_contact(PHONE)

    receipt = await adapter.send_text(PHONE, "Hola")

    assert ("POST", "/contacts") not in [(m, p) for m, p, _ in server.log]
    assert server.conversations[receipt.conversation_id].contact_id == contact_id


async def test_superstring_match_is_not_used_and_exact_contact_is_created(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    other_id = server.add_contact(SUPERSTRING_PHONE)

    receipt = await adapter.send_text(PHONE, "Hola")

    created = _request_body(server, "POST", "/contacts")
    assert created["phone_number"] == PHONE.value
    assert created["inbox_id"] == INBOX_ID
    contact_id = server.conversations[receipt.conversation_id].contact_id
    assert contact_id != other_id
    assert server.contacts[contact_id].phone_number == PHONE.value


async def test_exact_contact_is_picked_among_several_results(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    server.add_contact(SUPERSTRING_PHONE)
    exact_id = server.add_contact(PHONE)
    server.add_contact(PhoneNumber("+5199911122"))

    receipt = await adapter.send_text(PHONE, "Hola")

    assert server.conversations[receipt.conversation_id].contact_id == exact_id
    assert ("POST", "/contacts") not in [(m, p) for m, p, _ in server.log]


async def test_search_query_carries_only_the_phone_digits(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    await adapter.send_text(PHONE, "Hola")

    searches = [r for r in server.requests if _relative(r.url.path) == "/contacts/search"]
    assert [dict(r.url.params) for r in searches] == [{"q": PHONE.digits}]


# ---------------------------------------------------------------------------
# Conversación: solo inbox y contacto, dentro de la cuenta configurada
# ---------------------------------------------------------------------------


async def test_conversation_request_has_only_inbox_and_contact(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    contact_id = server.add_contact(PHONE)

    await adapter.send_text(PHONE, "Hola")

    assert _request_body(server, "POST", "/conversations") == {
        "inbox_id": INBOX_ID,
        "contact_id": contact_id,
    }


async def test_every_request_is_scoped_to_the_configured_account(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    await adapter.send_text(PHONE, "Hola")

    assert server.requests
    assert all(r.url.path.startswith(f"/api/v1/accounts/{ACCOUNT_ID}/") for r in server.requests)


async def test_same_phone_shares_a_conversation_and_other_phone_does_not(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    first = await adapter.send_text(PHONE, "Uno")
    second = await adapter.send_text(PHONE, "Dos")
    third = await adapter.send_text(OTHER_PHONE, "Tres")

    assert first.conversation_id == second.conversation_id
    assert third.conversation_id != first.conversation_id
    assert len({first.message_id, second.message_id, third.message_id}) == 3


async def test_without_lock_every_resolution_opens_a_new_conversation(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    """Sin `lock_to_single_conversation` el adaptador no reutiliza nada por su cuenta."""

    server.lock_to_single_conversation = False

    first = await adapter.send_text(PHONE, "Uno")
    second = await adapter.send_text(PHONE, "Dos")

    assert first.conversation_id != second.conversation_id


# ---------------------------------------------------------------------------
# Ventana de servicio
# ---------------------------------------------------------------------------


@FREE_FORM_SENDS
async def test_closed_window_rejects_free_form_sends_without_posting(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter, send: Send
) -> None:
    server.window_open = False

    with pytest.raises(ServiceWindowClosedError) as raised:
        await send(adapter, PHONE)

    assert raised.value.code == "service-window-closed"
    assert _message_posts(server) == []


async def test_closed_window_still_accepts_templates(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    server.window_open = False

    receipt = await adapter.send_template(PHONE, "otp_firma", {"code": "123456"})

    assert receipt.message_id
    assert len(_message_posts(server)) == 1


async def test_template_skips_the_window_read_even_when_creation_omits_can_reply(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    server.conversation_create_has_can_reply = False

    await adapter.send_template(PHONE, "otp_firma", {"code": "123456"})

    assert [m for m, p, _ in server.log if m == "GET" and p.startswith("/conversations/")] == []


async def test_open_window_sends_free_form(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    receipt = await adapter.send_text(PHONE, "Hola")

    assert receipt.conversation_id in server.conversations
    assert len(_message_posts(server)) == 1


async def test_brand_new_conversation_without_incoming_message_is_closed(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    server.new_conversation_can_reply = False

    with pytest.raises(ServiceWindowClosedError):
        await adapter.send_text(PHONE, "Hola")

    assert _message_posts(server) == []


@pytest.mark.parametrize("window_open", [True, False])
async def test_creation_without_can_reply_triggers_exactly_one_conversation_read(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter, window_open: bool
) -> None:
    server.conversation_create_has_can_reply = False
    server.window_open = window_open

    if window_open:
        receipt = await adapter.send_text(PHONE, "Hola")
        conversation_id = receipt.conversation_id
    else:
        with pytest.raises(ServiceWindowClosedError):
            await adapter.send_text(PHONE, "Hola")
        conversation_id = next(iter(server.conversations))

    reads = [e for e in server.log if e[:2] == ("GET", f"/conversations/{conversation_id}")]
    assert len(reads) == 1


async def test_creation_with_can_reply_needs_no_conversation_read(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    await adapter.send_text(PHONE, "Hola")

    assert [e for e in server.log if e[0] == "GET" and e[1].startswith("/conversations/")] == []


async def test_conversation_read_without_can_reply_is_unavailable_not_closed(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    server.conversation_create_has_can_reply = False
    server.conversation_has_can_reply = False

    with pytest.raises(MessagingUnavailableError):
        await adapter.send_text(PHONE, "Hola")

    assert _message_posts(server) == []


# ---------------------------------------------------------------------------
# Tokens por llamada
# ---------------------------------------------------------------------------


async def test_message_post_uses_the_bot_token_and_resolution_uses_the_agent_token(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    server.conversation_create_has_can_reply = False

    await adapter.send_text(PHONE, "Hola")

    assert [(method, path.split("/")[1], token) for method, path, token in server.log] == [
        ("GET", "contacts", "agent"),
        ("POST", "contacts", "agent"),
        ("POST", "conversations", "agent"),
        ("GET", "conversations", "agent"),
        ("POST", "conversations", "bot"),
    ]
    assert _message_posts(server) == [("POST", "/conversations/1/messages", "bot")]
    assert all("authorization" not in r.headers for r in server.requests)


# ---------------------------------------------------------------------------
# Envíos: cuerpos de las peticiones y recibos
# ---------------------------------------------------------------------------

_MESSAGES_PATH = "/conversations/1/messages"


async def test_send_text_posts_a_public_outgoing_message(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    await adapter.send_text(PHONE, "Hola")

    assert _request_body(server, "POST", _MESSAGES_PATH) == {
        "content": "Hola",
        "message_type": "outgoing",
        "private": False,
    }


async def test_receipt_carries_the_chatwoot_id_and_an_ordered_utc_time(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    first = await adapter.send_text(PHONE, "Uno")
    second = await adapter.send_text(PHONE, "Dos")

    assert first == MessageReceipt("1", 1, datetime(2026, 10, 12, 14, 0, 1, 1, tzinfo=UTC))
    assert second == MessageReceipt("2", 1, datetime(2026, 10, 12, 14, 0, 2, 2, tzinfo=UTC))
    assert first.sent_at < second.sent_at
    assert WAMID not in (first.message_id, second.message_id)
    assert len(first.message_id) <= 64


async def test_send_interactive_list_flattens_rows_into_input_select_items(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    sections = (
        ListSection(
            "Paquetes",
            (ListRow("pkg-1", "Show infantil", "Duración 2 h"), ListRow("pkg-2", "Show de magia")),
        ),
        ListSection("Extras", (ListRow("ext-1", "Globos"),)),
    )

    with capture_logs() as logs:
        receipt = await adapter.send_interactive_list(PHONE, "Elige", sections)

    assert receipt.message_id == "1"
    assert _request_body(server, "POST", _MESSAGES_PATH) == {
        "content": "Elige",
        "message_type": "outgoing",
        "private": False,
        "content_type": "input_select",
        "content_attributes": {
            "items": [
                {"title": "Show infantil", "value": "pkg-1"},
                {"title": "Show de magia", "value": "pkg-2"},
                {"title": "Globos", "value": "ext-1"},
            ]
        },
    }
    flattened = [entry for entry in logs if entry["event"] == "chatwoot_list_flattened"]
    assert len(flattened) == 1
    assert (flattened[0]["sections"], flattened[0]["rows"]) == (2, 3)
    assert "Show infantil" not in repr(logs)
    assert "Duración" not in repr(logs)


@pytest.mark.parametrize(
    ("language", "category"), [("es", "UTILITY"), ("en_US", "MARKETING")], ids=["es", "en"]
)
async def test_send_template_posts_name_params_category_and_language(
    server: FakeChatwootServer, language: str, category: str
) -> None:
    adapter = ChatwootMessagingAdapter(
        server.client(), inbox_id=INBOX_ID, template_language=language, template_category=category
    )

    await adapter.send_template(PHONE, "otp_firma", {"code": "123456"})

    assert _request_body(server, "POST", _MESSAGES_PATH) == {
        "content": "[plantilla:otp_firma]",
        "message_type": "outgoing",
        "private": False,
        "template_params": {
            "name": "otp_firma",
            "category": category,
            "language": language,
            "processed_params": {"body": {"code": "123456"}},
        },
    }


@pytest.mark.parametrize("caption", ["Tu cotización", None], ids=["with-caption", "no-caption"])
async def test_send_attachment_posts_a_multipart_file_with_optional_caption(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter, caption: str | None
) -> None:
    receipt = await adapter.send_attachment(
        PHONE, b"%PDF-1.4", "cotizacion.pdf", "application/pdf", caption
    )

    request = next(r for r in server.requests if _relative(r.url.path) == _MESSAGES_PATH)
    assert request.headers["content-type"].startswith("multipart/form-data")
    parts = {part.name: part for part in parse_multipart(request)}
    file_part = parts["attachments[]"]
    assert (file_part.filename, file_part.content_type, file_part.data) == (
        "cotizacion.pdf",
        "application/pdf",
        b"%PDF-1.4",
    )
    assert parts["message_type"].data == b"outgoing"
    if caption is None:
        assert "content" not in parts
    else:
        assert parts["content"].data == caption.encode()
    assert receipt.message_id == "1"


# ---------------------------------------------------------------------------
# Errores del envío: transitorios y sin datos sensibles
# ---------------------------------------------------------------------------


async def _send_template(adapter: ChatwootMessagingAdapter, to: PhoneNumber) -> MessageReceipt:
    return await adapter.send_template(to, "otp_firma", {"code": "123456"})


ALL_SENDS = pytest.mark.parametrize(
    "send",
    [_send_text, _send_list, _send_template, _send_attachment],
    ids=["text", "list", "template", "attachment"],
)


def _fail_with_timeout(server: FakeChatwootServer) -> None:
    server.message_post_error = httpx.ReadTimeout("simulado")


def _fail_with_connect_error(server: FakeChatwootServer) -> None:
    server.message_post_error = httpx.ConnectError("simulado")


def _fail_with_status(status: int) -> Callable[[FakeChatwootServer], None]:
    def fail(server: FakeChatwootServer) -> None:
        server.message_post_status = status

    return fail


FAILURES = pytest.mark.parametrize(
    "fail",
    [
        _fail_with_timeout,
        _fail_with_connect_error,
        _fail_with_status(502),
        _fail_with_status(422),
        _fail_with_status(401),
        _fail_with_status(404),
    ],
    ids=["timeout", "connect-error", "502", "422", "401", "404"],
)


@FAILURES
@ALL_SENDS
async def test_send_failures_are_transient_messaging_errors(
    server: FakeChatwootServer,
    adapter: ChatwootMessagingAdapter,
    send: Send,
    fail: Callable[[FakeChatwootServer], None],
) -> None:
    fail(server)

    with pytest.raises(MessagingUnavailableError):
        await send(adapter, PHONE)


@FAILURES
async def test_failed_send_leaks_neither_content_nor_phone_nor_tokens(
    server: FakeChatwootServer,
    adapter: ChatwootMessagingAdapter,
    fail: Callable[[FakeChatwootServer], None],
) -> None:
    fail(server)

    with capture_logs() as logs, pytest.raises(MessagingUnavailableError) as raised:
        await adapter.send_text(PHONE, "Codigo 123456")

    assert logs
    for output in (str(raised.value), repr(raised.value), repr(logs)):
        for secret in ("123456", "Codigo", PHONE.digits, BOT_TOKEN, AGENT_TOKEN):
            assert secret not in output


async def test_successful_send_logs_neither_content_nor_phone_nor_tokens(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    with capture_logs() as logs:
        await adapter.send_text(PHONE, "Codigo 123456")
        await adapter.send_template(PHONE, "otp_firma", {"code": "654321"})

    for secret in ("123456", "654321", "Codigo", PHONE.digits, BOT_TOKEN, AGENT_TOKEN):
        assert secret not in repr(logs)


# ---------------------------------------------------------------------------
# Estado de la conversación
# ---------------------------------------------------------------------------


def _request_bodies(server: FakeChatwootServer, method: str, path: str) -> list[dict[str, Any]]:
    return [
        json.loads(r.content)
        for r in server.requests
        if r.method == method and _relative(r.url.path) == path
    ]


def _list_requests(server: FakeChatwootServer) -> list[httpx.Request]:
    return [
        r
        for r in server.requests
        if r.method == "GET" and _relative(r.url.path) == "/conversations"
    ]


def _phone(number: int) -> PhoneNumber:
    return PhoneNumber(f"+51{900_000_000 + number}")


async def test_set_conversation_status_toggles_open_then_pending_with_the_agent_token(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    receipt = await adapter.send_text(PHONE, "Hola")
    conversation = server.conversations[receipt.conversation_id]
    path = f"/conversations/{receipt.conversation_id}/toggle_status"
    server.log.clear()

    to_human = await adapter.set_conversation_status(
        receipt.conversation_id, ConversationStatus.HUMAN
    )
    status_after_human = conversation.status
    to_bot = await adapter.set_conversation_status(receipt.conversation_id, ConversationStatus.BOT)

    assert (to_human, to_bot) == (None, None)
    assert (status_after_human, conversation.status) == ("open", "pending")
    assert _request_bodies(server, "POST", path) == [{"status": "open"}, {"status": "pending"}]
    assert server.log == [("POST", path, "agent"), ("POST", path, "agent")]


async def test_set_status_of_unknown_conversation_is_not_found(
    adapter: ChatwootMessagingAdapter,
) -> None:
    with pytest.raises(ResourceNotFoundError):
        await adapter.set_conversation_status(999_999, ConversationStatus.HUMAN)


# ---------------------------------------------------------------------------
# list_conversations: filtro, orden, paginación y resumen
# ---------------------------------------------------------------------------


async def test_list_conversations_returns_only_pending_and_open_most_recent_first(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    pending = server.add_conversation(PHONE, status="pending")
    server.add_conversation(_phone(1), status="resolved")
    opened = server.add_conversation(OTHER_PHONE, status="open")
    server.add_conversation(_phone(2), status="snoozed")

    result = await adapter.list_conversations()

    assert [(item.conversation_id, item.status) for item in result] == [
        (opened.id, ConversationStatus.HUMAN),
        (pending.id, ConversationStatus.BOT),
    ]
    assert [item.phone for item in result] == [OTHER_PHONE, PHONE]


@pytest.mark.parametrize(
    ("status", "chatwoot_status", "expected"),
    [
        (ConversationStatus.BOT, "pending", ["pending"]),
        (ConversationStatus.HUMAN, "open", ["open"]),
        (None, "all", ["open", "pending"]),
    ],
    ids=["bot", "human", "both"],
)
async def test_list_conversations_filters_by_status(
    server: FakeChatwootServer,
    adapter: ChatwootMessagingAdapter,
    status: ConversationStatus | None,
    chatwoot_status: str,
    expected: list[str],
) -> None:
    server.add_conversation(PHONE, status="pending")
    server.add_conversation(OTHER_PHONE, status="open")

    result = await adapter.list_conversations(status=status)

    assert sorted(server.conversations[item.conversation_id].status for item in result) == expected
    assert [r.url.params["status"] for r in _list_requests(server)] == [chatwoot_status]


async def test_list_conversations_returns_an_empty_tuple_when_nothing_matches(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    server.add_conversation(PHONE, status="pending")
    server.add_conversation(OTHER_PHONE, status="resolved")

    assert await adapter.list_conversations(status=ConversationStatus.HUMAN) == ()


async def test_list_conversations_is_restricted_to_the_inbox_and_sorted_by_activity(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    mine = server.add_conversation(PHONE)
    server.add_conversation(OTHER_PHONE, inbox_id=INBOX_ID + 1)

    result = await adapter.list_conversations()

    assert [item.conversation_id for item in result] == [mine.id]
    (request,) = _list_requests(server)
    assert dict(request.url.params) == {
        "inbox_id": str(INBOX_ID),
        "status": "all",
        "page": "1",
        "sort_by": "last_activity_at_desc",
    }


@pytest.mark.parametrize(
    ("page", "page_size", "expected_ids", "chatwoot_pages"),
    [
        (1, 7, list(range(60, 53, -1)), 1),
        (2, 25, list(range(35, 10, -1)), 2),
        (3, 10, list(range(40, 30, -1)), 2),
        (3, 25, list(range(10, 0, -1)), 3),
        (4, 25, [], 3),
    ],
    ids=["first-short-page", "second-page-of-25", "third-page-of-10", "last-partial", "past-end"],
)
async def test_list_conversations_applies_page_and_page_size_to_the_recency_sequence(
    server: FakeChatwootServer,
    adapter: ChatwootMessagingAdapter,
    page: int,
    page_size: int,
    expected_ids: list[int],
    chatwoot_pages: int,
) -> None:
    for number in range(1, 61):
        server.add_conversation(_phone(number))

    result = await adapter.list_conversations(page=page, page_size=page_size)

    assert [item.conversation_id for item in result] == expected_ids
    assert len(_list_requests(server)) == chatwoot_pages


async def test_list_conversations_pages_over_the_filtered_sequence_not_over_chatwoot_pages(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    for number in range(1, 61):
        server.add_conversation(_phone(number), status="resolved" if number % 2 == 0 else "pending")

    result = await adapter.list_conversations(page=2, page_size=10)

    assert [item.conversation_id for item in result] == list(range(39, 19, -2))


async def test_list_conversations_summary_reports_window_and_last_message_time(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    with_message = server.add_conversation(PHONE)
    server.add_message(with_message.id, "Hola")
    only_activity = server.add_conversation(OTHER_PHONE, can_reply=False)
    only_activity.last_activity_at = FIRST_EPOCH + 500
    nothing = server.add_conversation(_phone(1))
    nothing.last_activity_at = None

    summaries = {item.conversation_id: item for item in await adapter.list_conversations()}

    assert summaries[with_message.id].service_window_open is True
    assert summaries[with_message.id].last_message_at == datetime(
        2026, 10, 12, 14, 0, 2, 1, tzinfo=UTC
    )
    assert summaries[only_activity.id].service_window_open is False
    assert summaries[only_activity.id].last_message_at == datetime(
        2026, 10, 12, 14, 8, 20, tzinfo=UTC
    )
    assert summaries[nothing.id].last_message_at is None


async def test_conversation_without_a_parsable_phone_is_skipped_and_logged_once(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    kept = server.add_conversation(PHONE)
    no_phone = server.add_conversation(None, status="pending")
    server.add_conversation(None, status="resolved")

    with capture_logs() as logs:
        result = await adapter.list_conversations()

    assert [item.conversation_id for item in result] == [kept.id]
    skipped = [entry for entry in logs if entry["event"] == "chatwoot_conversation_skipped"]
    assert [entry["conversation_id"] for entry in skipped] == [no_phone.id]
    assert PHONE.digits not in repr(logs)


async def test_list_conversations_stops_at_a_short_page(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    for number in range(1, 31):
        server.add_conversation(_phone(number))

    result = await adapter.list_conversations(page_size=100)

    assert len(result) == 30
    assert len(_list_requests(server)) == 2


async def test_list_conversations_scan_is_capped_and_logged(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    for number in range(1, 521):
        server.add_conversation(_phone(number))

    with capture_logs() as logs:
        result = await adapter.list_conversations(page_size=600)

    assert len(result) == 500
    assert len(_list_requests(server)) == 20
    truncated = [entry for entry in logs if entry["event"] == "chatwoot_scan_truncated"]
    assert len(truncated) == 1


async def test_list_conversations_with_a_non_positive_page_size_makes_no_request(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    server.add_conversation(PHONE)

    assert await adapter.list_conversations(page_size=0) == ()
    assert _list_requests(server) == []


async def test_status_and_list_calls_use_only_the_agent_token(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    conversation = server.add_conversation(PHONE)

    await adapter.list_conversations()
    await adapter.set_conversation_status(conversation.id, ConversationStatus.HUMAN)

    assert {token for _, _, token in server.log} == {"agent"}


# ---------------------------------------------------------------------------
# list_messages: cursor por id, orden cronológico y filtrado
# ---------------------------------------------------------------------------


def _message_list_requests(server: FakeChatwootServer, conversation_id: int) -> list[httpx.Request]:
    path = f"/conversations/{conversation_id}/messages"
    return [r for r in server.requests if r.method == "GET" and _relative(r.url.path) == path]


def _fill(server: FakeChatwootServer, conversation_id: int, count: int) -> None:
    for number in range(1, count + 1):
        server.add_message(conversation_id, f"m{number}")


async def test_list_messages_is_chronological_limited_and_exclusive_on_before(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    first = await adapter.send_text(PHONE, "Uno")
    await adapter.send_text(PHONE, "Dos")
    last = await adapter.send_text(PHONE, "Tres")

    everything = await adapter.list_messages(first.conversation_id)
    newest_two = await adapter.list_messages(first.conversation_id, limit=2)
    older = await adapter.list_messages(first.conversation_id, before=last.sent_at)

    assert [m.body for m in everything] == ["Uno", "Dos", "Tres"]
    assert [m.body for m in newest_two] == ["Dos", "Tres"]
    assert [m.body for m in older] == ["Uno", "Dos"]
    assert [m.sent_at for m in everything] == sorted(m.sent_at for m in everything)
    assert everything[-1].sent_at == last.sent_at
    reads = [(m, t) for m, path, t in server.log if m == "GET" and path.endswith("/messages")]
    assert reads and {token for _, token in reads} == {"agent"}


@pytest.mark.parametrize(
    ("limit", "expected_first", "expected_cursors"),
    [(45, 1, [None, "26", "6"]), (30, 16, [None, "26"]), (20, 26, [None])],
    ids=["three-pages", "two-pages", "one-full-page"],
)
async def test_list_messages_pages_backwards_with_an_id_cursor_and_no_duplicates(
    server: FakeChatwootServer,
    adapter: ChatwootMessagingAdapter,
    limit: int,
    expected_first: int,
    expected_cursors: list[str | None],
) -> None:
    conversation = server.add_conversation(PHONE)
    _fill(server, conversation.id, 45)

    result = await adapter.list_messages(conversation.id, limit=limit)

    assert [m.body for m in result] == [f"m{n}" for n in range(expected_first, 46)]
    assert len({m.message_id for m in result}) == len(result)
    requests = _message_list_requests(server, conversation.id)
    assert [r.url.params.get("before") for r in requests] == expected_cursors


async def test_list_messages_stops_after_a_short_page_when_history_is_exhausted(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    conversation = server.add_conversation(PHONE)
    _fill(server, conversation.id, 5)

    result = await adapter.list_messages(conversation.id, limit=50)

    assert [m.body for m in result] == ["m1", "m2", "m3", "m4", "m5"]
    assert len(_message_list_requests(server, conversation.id)) == 1


async def test_list_messages_stops_after_an_empty_page_when_the_last_page_was_full(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    conversation = server.add_conversation(PHONE)
    _fill(server, conversation.id, 20)

    result = await adapter.list_messages(conversation.id, limit=50)

    assert len(result) == 20
    requests = _message_list_requests(server, conversation.id)
    assert [r.url.params.get("before") for r in requests] == [None, "1"]


async def test_list_messages_keeps_directions_and_attachments_and_drops_activity_and_notes(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    conversation = server.add_conversation(PHONE)
    server.add_message(conversation.id, "Gracias", message_type=0)
    server.add_message(conversation.id, "Cambio de estado", message_type=2)
    server.add_message(conversation.id, "Nota interna", private=True)
    server.add_message(
        conversation.id,
        "Tu cotización",
        attachment_url="https://files.example.org/storage/cotizacion%20final.pdf",
    )

    result = await adapter.list_messages(conversation.id)

    assert [(m.body, m.direction, m.attachment_filename) for m in result] == [
        ("Gracias", MessageDirection.INCOMING, None),
        ("Tu cotización", MessageDirection.OUTGOING, "cotizacion final.pdf"),
    ]
    assert all(m.conversation_id == conversation.id for m in result)


async def test_a_sent_attachment_is_listed_with_its_filename(
    adapter: ChatwootMessagingAdapter,
) -> None:
    receipt = await adapter.send_attachment(
        PHONE, b"%PDF", "cotizacion.pdf", "application/pdf", None
    )

    (message,) = await adapter.list_messages(receipt.conversation_id)

    assert message.attachment_filename == "cotizacion.pdf"
    assert message.message_id == receipt.message_id


async def test_list_messages_before_an_older_instant_returns_nothing(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    conversation = server.add_conversation(PHONE)
    _fill(server, conversation.id, 3)

    assert await adapter.list_messages(conversation.id) != ()
    assert (
        await adapter.list_messages(conversation.id, before=datetime(2000, 1, 1, tzinfo=UTC)) == ()
    )


async def test_list_messages_of_an_unknown_conversation_is_not_found(
    adapter: ChatwootMessagingAdapter,
) -> None:
    with pytest.raises(ResourceNotFoundError):
        await adapter.list_messages(999_999)


@pytest.mark.parametrize("limit", [0, -3])
async def test_list_messages_with_a_non_positive_limit_still_reads_once_and_returns_nothing(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter, limit: int
) -> None:
    conversation = server.add_conversation(PHONE)
    _fill(server, conversation.id, 3)

    assert await adapter.list_messages(conversation.id, limit=limit) == ()
    assert len(_message_list_requests(server, conversation.id)) == 1
    with pytest.raises(ResourceNotFoundError):
        await adapter.list_messages(999_999, limit=limit)


async def test_list_messages_scan_is_capped_and_logged(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    conversation = server.add_conversation(PHONE)
    _fill(server, conversation.id, 600)

    with capture_logs() as logs:
        result = await adapter.list_messages(conversation.id, limit=600)

    assert len(result) == 500
    assert result[-1].body == "m600"
    assert len(_message_list_requests(server, conversation.id)) == 25
    truncated = [entry for entry in logs if entry["event"] == "chatwoot_scan_truncated"]
    assert len(truncated) == 1


async def test_same_second_messages_are_not_skipped_when_paging_with_before(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    conversation = server.add_conversation(PHONE)
    for number in range(1, 26):
        server.add_message(conversation.id, f"m{number}", created_at=FIRST_EPOCH + 100)
    everything = await adapter.list_messages(conversation.id, limit=25)

    first_page = await adapter.list_messages(
        conversation.id, before=everything[20].sent_at, limit=10
    )
    second_page = await adapter.list_messages(
        conversation.id, before=first_page[0].sent_at, limit=10
    )

    assert [m.body for m in first_page] == [f"m{n}" for n in range(11, 21)]
    assert [m.body for m in second_page] == [f"m{n}" for n in range(1, 11)]
    assert len({m.sent_at for m in everything}) == 25


async def test_list_messages_failures_are_transient_and_leak_nothing(
    server: FakeChatwootServer, adapter: ChatwootMessagingAdapter
) -> None:
    conversation = server.add_conversation(PHONE)
    server.add_message(conversation.id, "Contenido reservado")
    server.down = True

    with capture_logs() as logs, pytest.raises(MessagingUnavailableError) as raised:
        await adapter.list_messages(conversation.id)

    for output in (str(raised.value), repr(logs)):
        for secret in (PHONE.digits, BOT_TOKEN, AGENT_TOKEN, "Contenido"):
            assert secret not in output


# ---------------------------------------------------------------------------
# Contrato del puerto y paridad entre el simulador y los fixtures
# ---------------------------------------------------------------------------


class TestChatwootMessagingAdapter(MessagingPortContract):
    """Suite de contrato de `IMessagingPort` sobre Chatwoot simulado, sin modificarla."""

    _server: FakeChatwootServer

    def make_adapter(self) -> IMessagingPort:
        self._server = FakeChatwootServer()
        return ChatwootMessagingAdapter(
            self._server.client(),
            inbox_id=INBOX_ID,
            template_language="es",
            template_category="UTILITY",
        )

    def close_service_window(self, adapter: IMessagingPort) -> None:
        self._server.window_open = False

    def make_unavailable(self, adapter: IMessagingPort) -> None:
        self._server.down = True


def _field_paths(value: Any, prefix: str = "") -> set[str]:
    """Rutas de campo de un JSON; los elementos de una lista se unen bajo `[]`."""

    paths: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else key
            paths.add(path)
            paths |= _field_paths(child, path)
    elif isinstance(value, list):
        for child in value:
            paths |= _field_paths(child, f"{prefix}[]")
    return paths


def _simulated_responses() -> dict[str, Any]:
    """Respuesta del simulador a cada llamada que tiene un fixture `api_*` equivalente."""

    server = FakeChatwootServer()
    server.add_contact(PHONE)
    http = httpx.Client(transport=httpx.MockTransport(server.handler), base_url=BASE_URL)

    def call(method: str, path: str, **kwargs: Any) -> Any:
        response = http.request(method, path, **kwargs)
        assert response.status_code == 200
        return response.json()

    created_contact = call(
        "POST",
        "/contacts",
        json={"inbox_id": INBOX_ID, "name": "Nuevo", "phone_number": "+51900000001"},
    )
    conversation = call("POST", "/conversations", json={"inbox_id": INBOX_ID, "contact_id": 1})
    message = call(
        "POST",
        f"/conversations/{conversation['id']}/messages",
        json={"content": "Hola", "message_type": "outgoing", "private": False},
    )
    server.add_message(
        conversation["id"],
        "Tu cotización",
        attachment_url="https://files.example.org/storage/cotizacion.pdf",
    )
    return {
        "api_contact_search": call("GET", "/contacts/search", params={"q": PHONE.digits}),
        "api_contact_created": created_contact,
        "api_conversation_created": conversation,
        "api_message_created": message,
        "api_conversation_list": call(
            "GET", "/conversations", params={"inbox_id": INBOX_ID, "status": "all"}
        ),
        "api_message_list": call("GET", f"/conversations/{conversation['id']}/messages"),
    }


# Los adjuntos no se capturaron: su forma (`attachments[].data_url`) sigue el código de Chatwoot.
_UNCAPTURED_PATHS = {"payload[].attachments", "payload[].attachments[].data_url"}


@pytest.mark.parametrize(
    "name",
    [
        "api_contact_search",
        "api_contact_created",
        "api_conversation_created",
        "api_message_created",
        "api_conversation_list",
        "api_message_list",
    ],
)
def test_every_field_the_simulator_renders_exists_in_the_matching_fixture(name: str) -> None:
    simulated = _field_paths(_simulated_responses()[name])
    captured = _field_paths(load_fixture(name)["body"])

    assert simulated
    assert simulated - captured - _UNCAPTURED_PATHS == set()
