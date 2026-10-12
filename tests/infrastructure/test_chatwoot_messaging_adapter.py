"""Adaptador de mensajería de Chatwoot: resolución de contacto y conversación, y ventana."""

import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from structlog.testing import capture_logs

from app.application.dtos.messaging_dto import ListRow, ListSection, MessageReceipt
from app.domain.exceptions.messaging_exceptions import (
    MessagingUnavailableError,
    ServiceWindowClosedError,
)
from app.domain.value_objects.phone_number import PhoneNumber
from app.infrastructure.adapters.secondary.external_services.chatwoot.chatwoot_messaging_adapter import (  # noqa: E501
    ChatwootMessagingAdapter,
)
from tests.infrastructure.chatwoot_support import (
    ACCOUNT_ID,
    AGENT_TOKEN,
    BOT_TOKEN,
    INBOX_ID,
    WAMID,
    FakeChatwootServer,
    parse_multipart,
)

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
