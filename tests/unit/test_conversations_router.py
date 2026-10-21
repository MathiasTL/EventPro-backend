"""Router de lectura de la bandeja: RBAC, filtros, 503/404 y orden de rutas (spec 09, 7 y 10)."""

from collections.abc import Iterator
from datetime import timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from app.application.dtos.messaging_dto import ConversationStatus
from app.application.services.audit_service import AuditService
from app.application.use_cases.messaging.conversation_assignment import (
    ReleaseConversation,
    TakeoverConversation,
)
from app.application.use_cases.messaging.conversation_views import ConversationViewBuilder
from app.application.use_cases.messaging.enqueue_message import EnqueueMessage
from app.application.use_cases.messaging.list_conversation_messages import (
    ListConversationMessages,
)
from app.application.use_cases.messaging.list_conversations import (
    GetConversation,
    ListConversations,
)
from app.application.use_cases.messaging.mark_conversation_read import MarkConversationRead
from app.application.use_cases.messaging.mark_event_done import MarkEventDone
from app.application.use_cases.messaging.retry_message import RetryMessage
from app.application.use_cases.messaging.send_conversation_message import (
    RetryConversationMessage,
    SendConversationMessage,
)
from app.domain.entities.conversation_link import ConversationLink
from app.domain.entities.quote import QuoteStatus
from app.domain.value_objects.outbox import OutboxStatus
from app.domain.value_objects.phone_number import PhoneNumber
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.secondary.cache.in_memory_conversation_session_adapter import (
    InMemoryConversationSessionAdapter,
)
from app.infrastructure.adapters.secondary.events.in_memory_conversation_event_publisher import (
    InMemoryConversationEventPublisher,
)
from app.infrastructure.adapters.secondary.external_services.fake_messaging_adapter import (
    FakeMessagingAdapter,
)
from app.infrastructure.di import containers
from app.main import create_app
from tests import auth_support
from tests.application.assignment_support import InMemoryAuditPort, InMemoryLinkUnitOfWork
from tests.application.conversation_link_support import InMemoryConversationLinkRepository
from tests.application.inbox_read_support import FakeInboxLookup
from tests.application.outbox_support import NOW, FixedClock, InMemoryOutboxStore
from tests.domain.outbox_support import make_message
from tests.unit.test_conversations_stream_router import OneEventSubscriber, _token

BASE = "/api/v1/conversations"
PHONE = PhoneNumber("+51999888777")
FIXED_DETAIL = "La mensajería no está disponible temporalmente."


class _Env:
    def __init__(self) -> None:
        self.messaging = FakeMessagingAdapter()
        self.messaging.receive_text(PHONE, "Hola", name="Carlos Ramírez")
        self.publisher = InMemoryConversationEventPublisher()
        self.lookup = FakeInboxLookup()
        self.links = InMemoryConversationLinkRepository()
        views = ConversationViewBuilder(self.links, self.lookup)
        outbox = InMemoryOutboxStore().repository()
        self.list = ListConversations(self.messaging, views)
        self.get = GetConversation(self.messaging, views)
        self.messages = ListConversationMessages(self.messaging, outbox, self.lookup)
        self.read = MarkConversationRead(self.messaging, views, self.publisher)
        self.event_done = MarkEventDone(
            self.messaging, self.links, views, self.publisher, FixedClock()
        )
        self.audit = InMemoryAuditPort()
        assignment_args = (
            self.messaging,
            InMemoryLinkUnitOfWork(self.links),
            views,
            InMemoryConversationSessionAdapter(),
            AuditService(self.audit),
            self.publisher,
            FixedClock(),
        )
        self.takeover = TakeoverConversation(*assignment_args)
        self.outbox_store = InMemoryOutboxStore()
        self.outbox = self.outbox_store.repository()
        clock = FixedClock()
        outgoing_args = (self.messaging, self.links, self.outbox, AuditService(self.audit))
        self.send = SendConversationMessage(*outgoing_args, EnqueueMessage(self.outbox, clock))
        self.retry = RetryConversationMessage(*outgoing_args, RetryMessage(self.outbox, clock))
        self.release = ReleaseConversation(*assignment_args)

    def link_quote(self, status: QuoteStatus) -> None:
        quote_id = uuid4()
        self.lookup.quotes[quote_id] = status
        link = ConversationLink.create(chatwoot_conversation_id=1, now=NOW)
        link.link_quote(quote_id, at=NOW)
        self.links.put(link)


@pytest.fixture
def env() -> _Env:
    return _Env()


@pytest.fixture
def app(env: _Env) -> Iterator[FastAPI]:
    application = create_app()
    auth_support.install(application)
    overrides = application.dependency_overrides
    overrides[containers.get_list_conversations_use_case] = lambda: env.list
    overrides[containers.get_get_conversation_use_case] = lambda: env.get
    overrides[containers.get_list_conversation_messages_use_case] = lambda: env.messages
    overrides[containers.get_mark_conversation_read_use_case] = lambda: env.read
    overrides[containers.get_mark_event_done_use_case] = lambda: env.event_done
    overrides[containers.get_takeover_conversation_use_case] = lambda: env.takeover
    overrides[containers.get_release_conversation_use_case] = lambda: env.release
    overrides[containers.get_send_conversation_message_use_case] = lambda: env.send
    overrides[containers.get_retry_conversation_message_use_case] = lambda: env.retry
    overrides[containers.get_conversation_event_subscriber] = lambda: OneEventSubscriber()
    auth_support.set_role(Role.ENCARGADO)
    yield application
    auth_support.set_role(Role.SUPERADMIN)


async def _request(
    app: FastAPI, method: str, path: str, *, user: UUID | None = None, **kwargs: object
) -> httpx.Response:
    token = _token() if user is None else _token(subject=user)
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        return await client.request(method, f"{BASE}{path}", headers=headers, **kwargs)  # type: ignore[arg-type]


async def test_list_returns_the_item_shape(app: FastAPI) -> None:
    response = await _request(app, "GET", "")

    assert response.status_code == 200
    body = response.json()
    assert (body["page"], body["page_size"], body["total"]) == (1, 20, 1)
    item = body["items"][0]
    assert item["chatwoot_conversation_id"] == 1
    assert item["client"] == {"id": None, "name": "Carlos Ramírez", "phone": PHONE.value}
    assert item["status"] == "pending"
    assert item["mode"] == "BOT"
    assert item["lead_status"] == "QUOTING"
    assert item["quote_status"] is None
    assert item["unread_count"] == 1
    assert set(item) >= {"assigned_user_name", "service_window_expires_at", "handoff_reason"}


async def test_superadmin_may_filter_by_assigned_user(app: FastAPI) -> None:
    auth_support.set_role(Role.SUPERADMIN)

    response = await _request(app, "GET", "", params={"assigned_user_id": str(uuid4())})

    assert response.status_code == 200
    assert response.json()["total"] == 0


async def test_encargado_cannot_filter_by_assigned_user(app: FastAPI) -> None:
    response = await _request(app, "GET", "", params={"assigned_user_id": str(uuid4())})

    assert response.status_code == 403
    assert response.json()["type"].endswith("/forbidden")


async def test_short_search_is_a_validation_error(app: FastAPI) -> None:
    response = await _request(app, "GET", "", params={"q": " a "})

    assert response.status_code == 422
    assert response.json()["type"].endswith("/validation-error")


async def test_search_and_filters_apply(app: FastAPI) -> None:
    hit = await _request(app, "GET", "", params={"q": "ramirez", "mode": "BOT"})
    miss = await _request(app, "GET", "", params={"q": "ramirez", "assigned": "unassigned"})

    assert hit.json()["total"] == 1
    assert miss.json()["total"] == 0


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", ""),
        ("GET", "/1"),
        ("GET", "/1/messages"),
        ("POST", "/1/read"),
        ("POST", "/1/takeover"),
        ("POST", "/1/release"),
        ("POST", "/1/messages"),
        ("POST", f"/1/messages/{uuid4()}/retry"),
    ],
)
async def test_operador_is_forbidden(app: FastAPI, method: str, path: str) -> None:
    auth_support.set_role(Role.OPERADOR)

    response = await _request(app, method, path)

    assert response.status_code == 403
    assert response.json()["type"].endswith("/forbidden")


async def test_get_conversation_and_not_found(app: FastAPI) -> None:
    ok = await _request(app, "GET", "/1")
    missing = await _request(app, "GET", "/999")

    assert ok.status_code == 200
    assert ok.json()["chatwoot_conversation_id"] == 1
    assert missing.status_code == 404
    assert missing.json()["type"].endswith("/not-found")


async def test_stream_is_still_reachable_before_the_id_route(app: FastAPI) -> None:
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        response = await client.get(f"{BASE}/stream", params={"access_token": _token()})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")


async def test_non_numeric_id_is_a_validation_error(app: FastAPI) -> None:
    assert (await _request(app, "GET", "/abc")).status_code == 422
    assert (await _request(app, "GET", "/0")).status_code == 422


async def test_messages_first_page_has_unsent_and_the_next_does_not(app: FastAPI) -> None:
    first = await _request(app, "GET", "/1/messages")
    older = await _request(app, "GET", "/1/messages", params={"before": 99})

    body = first.json()
    assert first.status_code == 200
    assert body["unsent"] == [] and body["has_more"] is False
    message = body["items"][0]
    assert message["author_type"] == "CLIENT"
    assert message["direction"] == "INCOMING"
    assert set(message) >= {"author_name", "failure_code", "outbox_id", "retryable"}
    assert "unsent" not in older.json()


async def test_message_attachments_use_the_eventpro_path(app: FastAPI, env: _Env) -> None:
    env.messaging.receive_attachment(PHONE, b"img", "foto.jpg", "image/jpeg")

    body = (await _request(app, "GET", "/1/messages")).json()

    attachment = body["items"][0]["attachments"][0]
    assert attachment["url"] == f"/api/v1/conversations/1/attachments/{attachment['id']}"
    assert "chatwoot" not in str(body).lower()


async def test_messages_limit_is_capped(app: FastAPI) -> None:
    assert (await _request(app, "GET", "/1/messages", params={"limit": 101})).status_code == 422


async def test_mark_read_returns_204_and_publishes(app: FastAPI, env: _Env) -> None:
    response = await _request(app, "POST", "/1/read")

    assert response.status_code == 204
    assert response.content == b""
    assert env.publisher.events[0].data["unread_count"] == 0
    assert (await _request(app, "POST", "/999/read")).status_code == 404


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", ""), ("GET", "/1"), ("GET", "/1/messages"), ("POST", "/1/read")],
)
async def test_gateway_unavailable_maps_to_503(
    app: FastAPI, env: _Env, method: str, path: str
) -> None:
    env.messaging.unavailable = True

    response = await _request(app, method, path)

    assert response.status_code == 503
    body = response.json()
    assert body["type"].endswith("/messaging-gateway-unavailable")
    assert body["detail"] == FIXED_DETAIL
    assert "chatwoot" not in str(body).lower()


async def test_the_503_mapping_is_not_global(app: FastAPI, env: _Env) -> None:
    """D10: fuera de este router el error no se traduce."""

    from app.domain.exceptions.messaging_exceptions import MessagingUnavailableError

    @app.get("/boom")
    async def boom() -> None:
        raise MessagingUnavailableError("x")

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t"
    ) as client:
        response = await client.get("/boom")

    assert response.status_code == 500


async def test_event_done_marks_a_converted_conversation_and_publishes(
    app: FastAPI, env: _Env
) -> None:
    env.link_quote(QuoteStatus.CONVERTED)

    response = await _request(app, "POST", "/1/lead/event-done")

    assert response.status_code == 200
    assert response.json()["lead_status"] == "EVENT_DONE"
    assert response.json()["quote_status"] == "CONVERTED"
    assert [e.data["lead_status"] for e in env.publisher.events] == ["EVENT_DONE"]
    assert env.links.links[1].event_done_by_user_id is not None


async def test_event_done_is_idempotent(app: FastAPI, env: _Env) -> None:
    env.link_quote(QuoteStatus.CONVERTED)
    await _request(app, "POST", "/1/lead/event-done")

    response = await _request(app, "POST", "/1/lead/event-done")

    assert response.status_code == 200
    assert response.json()["lead_status"] == "EVENT_DONE"


async def test_event_done_from_another_status_is_a_409_problem(app: FastAPI, env: _Env) -> None:
    env.link_quote(QuoteStatus.SENT)

    response = await _request(app, "POST", "/1/lead/event-done")

    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"].endswith("/invalid-lead-transition")
    assert env.publisher.events == []


async def test_event_done_for_a_missing_conversation_is_404(app: FastAPI) -> None:
    response = await _request(app, "POST", "/999/lead/event-done")

    assert response.status_code == 404
    assert response.json()["type"].endswith("/not-found")


async def test_event_done_is_forbidden_for_an_operator(app: FastAPI, env: _Env) -> None:
    env.link_quote(QuoteStatus.CONVERTED)
    auth_support.set_role(Role.OPERADOR)

    response = await _request(app, "POST", "/1/lead/event-done")

    assert response.status_code == 403
    assert 1 not in {k for k, v in env.links.links.items() if v.event_done_at}


# --- takeover y release (B6) ----------------------------------------------------------------


async def test_takeover_returns_the_updated_item_and_publishes(app: FastAPI, env: _Env) -> None:
    response = await _request(app, "POST", "/1/takeover")

    assert response.status_code == 200
    body = response.json()
    assert (body["status"], body["mode"]) == ("open", "HUMAN")
    assert body["assigned_user_id"] == str(env.links.links[1].assigned_user_id)
    assert body["handoff_reason"] == "MANUAL_TAKEOVER"
    assert [e.data["status"] for e in env.publisher.events] == ["open"]


async def test_takeover_of_another_encargados_conversation_is_a_409_with_the_assignee(
    app: FastAPI, env: _Env
) -> None:
    owner = uuid4()
    await env.messaging.set_conversation_status(1, ConversationStatus.HUMAN)
    env.links.put(ConversationLink.create(chatwoot_conversation_id=1, now=NOW))
    await env.links.claim(1, owner, None)

    response = await _request(app, "POST", "/1/takeover")

    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"].endswith("/conversation-taken-by-other")
    assert response.json()["assigned_user_id"] == str(owner)


async def test_takeover_with_the_gateway_down_is_a_503_and_not_found_is_a_404(
    app: FastAPI, env: _Env
) -> None:
    missing = await _request(app, "POST", "/999/takeover")
    env.messaging.status_update_fails = True
    failed = await _request(app, "POST", "/1/takeover")

    assert missing.status_code == 404
    assert missing.json()["type"].endswith("/not-found")
    assert failed.status_code == 503
    assert failed.json()["type"].endswith("/messaging-gateway-unavailable")
    assert failed.json()["detail"] == FIXED_DETAIL
    assert env.links.links[1].assigned_user_id is None


async def test_release_returns_the_item_in_bot_mode(app: FastAPI, env: _Env) -> None:
    user = uuid4()
    await _request(app, "POST", "/1/takeover", user=user)

    response = await _request(app, "POST", "/1/release", user=user)

    assert response.status_code == 200
    body = response.json()
    assert (body["status"], body["mode"], body["assigned_user_id"]) == ("pending", "BOT", None)
    assert body["handoff_reason"] == "MANUAL_TAKEOVER"


async def test_release_of_an_unassigned_open_conversation_is_a_409_not_taken(
    app: FastAPI, env: _Env
) -> None:
    await env.messaging.set_conversation_status(1, ConversationStatus.HUMAN)

    response = await _request(app, "POST", "/1/release")

    assert response.status_code == 409
    assert response.json()["type"].endswith("/conversation-not-taken")


async def test_superadmin_reassignment_through_the_endpoint_is_audited(
    app: FastAPI, env: _Env
) -> None:
    owner = uuid4()
    await env.messaging.set_conversation_status(1, ConversationStatus.HUMAN)
    env.links.put(ConversationLink.create(chatwoot_conversation_id=1, now=NOW))
    await env.links.claim(1, owner, None)
    auth_support.set_role(Role.SUPERADMIN)

    response = await _request(app, "POST", "/1/takeover")

    assert response.status_code == 200
    assert [e.action for e in env.audit.entries] == ["OVERRIDE_CONVERSATION_ASSIGNMENT"]


# --- enviar y reintentar (B7) ---------------------------------------------------------------


async def _taken_by(app: FastAPI) -> UUID:
    user = uuid4()
    await _request(app, "POST", "/1/takeover", user=user)
    return user


async def test_send_returns_202_queued_and_audits_the_author(app: FastAPI, env: _Env) -> None:
    user = await _taken_by(app)

    response = await _request(app, "POST", "/1/messages", user=user, json={"content": "Hola"})

    assert response.status_code == 202
    body = response.json()
    assert (body["chatwoot_conversation_id"], body["delivery_status"]) == (1, "QUEUED")
    row = env.outbox_store.messages[UUID(body["outbox_id"])]
    assert row.author_user_id == user
    assert env.links.links[1].assigned_user_id == user


async def test_send_without_taking_the_conversation_is_a_409(app: FastAPI) -> None:
    response = await _request(app, "POST", "/1/messages", json={"content": "Hola"})

    assert response.status_code == 409
    assert response.json()["type"].endswith("/conversation-not-taken")


async def test_send_to_another_encargados_conversation_is_a_409_with_the_assignee(
    app: FastAPI,
) -> None:
    owner = await _taken_by(app)

    response = await _request(app, "POST", "/1/messages", json={"content": "Hola"})

    assert response.status_code == 409
    assert response.json()["type"].endswith("/conversation-taken-by-other")
    assert response.json()["assigned_user_id"] == str(owner)


async def test_send_with_the_window_closed_is_a_422_with_the_expiry(
    app: FastAPI, env: _Env
) -> None:
    user = await _taken_by(app)
    link = env.links.links[1]
    link.last_client_message_at = NOW - timedelta(hours=30)
    env.links.put(link)
    env.messaging.service_window_open = False

    response = await _request(app, "POST", "/1/messages", user=user, json={"content": "Hola"})

    assert response.status_code == 422
    body = response.json()
    assert body["type"].endswith("/service-window-closed")
    assert body["service_window_expires_at"] == (NOW - timedelta(hours=6)).isoformat()
    assert env.outbox_store.messages == {}


@pytest.mark.parametrize(
    "body",
    [
        {"template": {"name": "contract_reminder", "language": "es", "params": {}}},
        {"content": "Hola", "template": {"name": "x"}},
        {},
        {"content": "   "},
        {"content": "Hola", "other": 1},
    ],
)
async def test_send_rejects_templates_and_empty_bodies_with_422(
    app: FastAPI, env: _Env, body: dict[str, object]
) -> None:
    user = await _taken_by(app)

    response = await _request(app, "POST", "/1/messages", user=user, json=body)

    assert response.status_code == 422
    assert response.json()["type"].endswith("/validation-error")
    assert env.outbox_store.messages == {}


async def test_send_with_the_gateway_down_is_a_503(app: FastAPI, env: _Env) -> None:
    user = await _taken_by(app)
    env.messaging.unavailable = True

    response = await _request(app, "POST", "/1/messages", user=user, json={"content": "Hola"})

    assert response.status_code == 503
    assert response.json()["detail"] == FIXED_DETAIL


async def _failed_row(env: _Env) -> UUID:
    message = make_message(recipient=PHONE)
    message.register_failure(error="caído", permanent=True, now=NOW)
    env.outbox_store.put(message)
    return message.id


async def test_retry_returns_202_for_a_failed_row(app: FastAPI, env: _Env) -> None:
    user = await _taken_by(app)
    row_id = await _failed_row(env)

    response = await _request(app, "POST", f"/1/messages/{row_id}/retry", user=user)

    assert response.status_code == 202
    assert response.json()["outbox_id"] == str(row_id)
    assert env.outbox_store.messages[row_id].status is OutboxStatus.PENDING
    (entry,) = env.audit.entries
    assert entry.new_values is not None and entry.new_values["retry_of"] == str(row_id)


async def test_retry_of_a_sent_or_pending_row_is_a_409_invalid_outbox_state(
    app: FastAPI, env: _Env
) -> None:
    user = await _taken_by(app)
    sent = make_message(recipient=PHONE)
    sent.mark_sent(external_message_id="cw-1", conversation_id=1, now=NOW)
    pending = make_message(recipient=PHONE)
    env.outbox_store.put(sent)
    env.outbox_store.put(pending)

    for row in (sent, pending):
        response = await _request(app, "POST", f"/1/messages/{row.id}/retry", user=user)
        assert response.status_code == 409
        assert response.json()["type"].endswith("/invalid-outbox-state")


async def test_retry_of_a_missing_row_is_a_404(app: FastAPI) -> None:
    user = await _taken_by(app)

    response = await _request(app, "POST", f"/1/messages/{uuid4()}/retry", user=user)

    assert response.status_code == 404
    assert response.json()["type"].endswith("/not-found")


async def test_retry_with_the_window_closed_is_a_422(app: FastAPI, env: _Env) -> None:
    user = await _taken_by(app)
    row_id = await _failed_row(env)
    env.messaging.service_window_open = False

    response = await _request(app, "POST", f"/1/messages/{row_id}/retry", user=user)

    assert response.status_code == 422
    assert response.json()["type"].endswith("/service-window-closed")
    assert env.outbox_store.messages[row_id].status is OutboxStatus.FAILED
