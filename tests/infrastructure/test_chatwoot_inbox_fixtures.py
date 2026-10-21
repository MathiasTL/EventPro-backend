"""Adaptador de Chatwoot contra las capturas reales de la bandeja (2026-10-20), sin simulador.

Cada ruta de la API responde con el cuerpo de un fixture saneado a través de `httpx.MockTransport`,
de modo que el adaptador lee exactamente lo que entregó Chatwoot v4.18.0.
"""

import httpx
import pytest

from app.application.dtos.messaging_dto import (
    ConversationLifecycle,
    ConversationStatus,
    MessageDirection,
    MessageSender,
)
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError
from app.infrastructure.adapters.secondary.external_services.chatwoot.chatwoot_client import (
    TOKEN_HEADER,
    ChatwootClient,
)
from app.infrastructure.adapters.secondary.external_services.chatwoot.chatwoot_messaging_adapter import (  # noqa: E501
    ChatwootMessagingAdapter,
)
from tests.chatwoot_fixture_support import load_fixture
from tests.infrastructure.chatwoot_support import (
    AGENT_TOKEN,
    BASE_URL,
    BOT_TOKEN,
    PUBLIC_HOST,
)

JPEG = b"\xff\xd8fixture-image"
_PREFIX = "/api/v1/accounts/1"
_ROUTES: dict[tuple[str, str], str] = {
    ("GET", "/conversations"): "api_inbox_conversation_list",
    ("GET", "/conversations/1"): "api_conversation_reopened",
    ("GET", "/conversations/1/messages"): "api_inbox_message_list",
    ("GET", "/conversations/3/messages"): "api_message_list_window_failed",
    ("POST", "/conversations/1/update_last_seen"): "api_update_last_seen",
}


class _Chatwoot:
    """Responde con fixtures y registra cada petición; el adjunto se sirve tras una redirección."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path.startswith("/rails/active_storage/blobs/redirect/"):
            return httpx.Response(302, headers={"location": "/rails/active_storage/disk/file"})
        if path.startswith("/rails/active_storage/disk/"):
            return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})
        fixture = _ROUTES.get((request.method, path.removeprefix(_PREFIX)))
        if fixture is None:
            return httpx.Response(404)
        return httpx.Response(200, json=load_fixture(fixture)["body"])


@pytest.fixture
def chatwoot() -> _Chatwoot:
    return _Chatwoot()


@pytest.fixture
def adapter(chatwoot: _Chatwoot) -> ChatwootMessagingAdapter:
    http = httpx.AsyncClient(transport=httpx.MockTransport(chatwoot.handler), base_url=BASE_URL)
    client = ChatwootClient(http, bot_token=BOT_TOKEN, agent_token=AGENT_TOKEN)
    return ChatwootMessagingAdapter(
        client, inbox_id=1, template_language="es", template_category="UTILITY"
    )


async def test_inbox_list_reports_unread_preview_window_and_assignee(
    adapter: ChatwootMessagingAdapter,
) -> None:
    summaries = {item.conversation_id: item for item in await adapter.list_conversations()}

    bot_handoff = summaries[1]
    assert bot_handoff.unread_count == 10
    assert bot_handoff.service_window_open is True
    assert (bot_handoff.lifecycle, bot_handoff.status) == (
        ConversationLifecycle.PENDING,
        ConversationStatus.BOT,
    )
    assert bot_handoff.contact_name == "Cliente Prueba"
    assert bot_handoff.last_message_preview == (
        "Con gusto. Un encargado continuará esta conversación en breve; gracias por tu paciencia."
    )
    # El último mensaje de la conversación 1 es un aviso de actividad posterior al del bot.
    assert bot_handoff.last_message_at is not None
    assert summaries[3].last_message_preview is None
    assert summaries[3].service_window_open is False
    assert summaries[2].assignee_name == "Encargado Prueba"


async def test_conversation_reopened_by_the_client_is_pending_with_unread(
    adapter: ChatwootMessagingAdapter,
) -> None:
    summary = await adapter.get_conversation(1)

    assert summary.lifecycle is ConversationLifecycle.PENDING
    assert summary.unread_count == 2
    assert summary.service_window_open is True


async def test_unknown_conversation_is_not_found(adapter: ChatwootMessagingAdapter) -> None:
    with pytest.raises(ResourceNotFoundError):
        await adapter.get_conversation(404)


async def test_messages_distinguish_bot_contact_activity_and_attachment(
    adapter: ChatwootMessagingAdapter,
) -> None:
    messages = {int(m.message_id): m for m in await adapter.list_messages(1)}

    assert (messages[26].direction, messages[26].sender) == (
        MessageDirection.INCOMING,
        MessageSender.CONTACT,
    )
    bot = messages[39]
    assert (bot.direction, bot.sender, bot.sender_name) == (
        MessageDirection.OUTGOING,
        MessageSender.AGENT_BOT,
        "EventPro Bot",
    )
    assert bot.status == "read"
    activity = messages[38]
    assert (activity.direction, activity.sender, activity.sender_name) == (
        MessageDirection.ACTIVITY,
        None,
        None,
    )
    image = messages[45]
    assert image.body is None
    (attachment,) = image.attachments
    assert (attachment.attachment_id, attachment.file_type) == (1, "image")
    assert (attachment.content_type, attachment.extension) == ("image/jpeg", "jpg")
    assert (attachment.file_size, attachment.filename) == (453744, "File.jpg")
    assert [int(m.message_id) for m in await adapter.list_messages(1)] == sorted(messages)


async def test_window_failure_has_a_chatwoot_text_and_no_meta_code(
    adapter: ChatwootMessagingAdapter,
) -> None:
    activity, failed = await adapter.list_messages(3)

    assert activity.direction is MessageDirection.ACTIVITY
    assert failed.status == "failed"
    assert failed.sender is MessageSender.USER
    assert failed.external_error is not None
    assert "24 horas" in failed.external_error
    assert "(#" not in failed.external_error


async def test_mark_read_posts_update_last_seen_with_the_agent_token(
    adapter: ChatwootMessagingAdapter, chatwoot: _Chatwoot
) -> None:
    await adapter.mark_conversation_read(1)

    (request,) = chatwoot.requests
    assert (request.method, request.url.path) == (
        "POST",
        f"{_PREFIX}/conversations/1/update_last_seen",
    )
    assert request.headers[TOKEN_HEADER] == AGENT_TOKEN


async def test_attachment_from_the_capture_is_downloaded_through_the_base_host(
    adapter: ChatwootMessagingAdapter, chatwoot: _Chatwoot
) -> None:
    content = await adapter.get_attachment(1, 1)

    assert (content.data, content.content_type, content.filename) == (
        JPEG,
        "image/jpeg",
        "File.jpg",
    )
    blob_requests = [r for r in chatwoot.requests if r.url.path.startswith("/rails/")]
    assert {r.url.host for r in blob_requests} == {"chatwoot.example.org"}
    assert {r.headers["host"] for r in blob_requests} == {PUBLIC_HOST}
    assert all(TOKEN_HEADER not in r.headers for r in blob_requests)


async def test_attachment_that_is_not_in_the_conversation_is_not_found(
    adapter: ChatwootMessagingAdapter,
) -> None:
    with pytest.raises(ResourceNotFoundError):
        await adapter.get_attachment(3, 1)
