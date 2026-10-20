from datetime import UTC, datetime

import pytest
from structlog.testing import capture_logs

from app.application.dtos.messaging_dto import ConversationStatus, MessageDirection
from app.application.ports.output.messaging_port import IMessagingPort
from app.domain.exceptions.messaging_exceptions import (
    MessagingUnavailableError,
    ServiceWindowClosedError,
)
from app.infrastructure.adapters.secondary.external_services.fake_messaging_adapter import (
    FakeMessagingAdapter,
    SentMessageKind,
)

from .messaging_port_contract import PHONE, SECTIONS, MessagingPortContract


class _FrozenClock:
    def utcnow(self) -> datetime:
        return datetime(2026, 10, 7, 15, 0, tzinfo=UTC)


class TestFakeMessagingAdapter(MessagingPortContract):
    def make_adapter(self) -> IMessagingPort:
        return FakeMessagingAdapter()

    def close_service_window(self, adapter: IMessagingPort) -> None:
        assert isinstance(adapter, FakeMessagingAdapter)
        adapter.service_window_open = False

    def make_unavailable(self, adapter: IMessagingPort) -> None:
        assert isinstance(adapter, FakeMessagingAdapter)
        adapter.unavailable = True


async def test_sent_log_records_each_kind_for_assertions() -> None:
    adapter = FakeMessagingAdapter()
    await adapter.send_text(PHONE, "Hola")
    await adapter.send_interactive_list(PHONE, "Elige", SECTIONS)
    await adapter.send_template(PHONE, "otp_firma", {"code": "123456"})
    await adapter.send_attachment(PHONE, b"12345", "a.pdf", "application/pdf", "Adjunto")
    assert [message.kind for message in adapter.sent] == [
        SentMessageKind.TEXT,
        SentMessageKind.INTERACTIVE_LIST,
        SentMessageKind.TEMPLATE,
        SentMessageKind.ATTACHMENT,
    ]
    assert adapter.sent[0].body == "Hola"
    assert adapter.sent[1].sections == SECTIONS
    assert adapter.sent[2].template_name == "otp_firma"
    assert adapter.sent[2].template_params == {"code": "123456"}
    assert adapter.sent[3].filename == "a.pdf"
    assert adapter.sent[3].size_bytes == 5
    assert all(message.to == PHONE for message in adapter.sent)


async def test_failed_sends_are_not_recorded() -> None:
    adapter = FakeMessagingAdapter()
    adapter.service_window_open = False
    with pytest.raises(ServiceWindowClosedError):
        await adapter.send_text(PHONE, "Hola")
    adapter.unavailable = True
    with pytest.raises(MessagingUnavailableError):
        await adapter.send_template(PHONE, "otp_firma", {})
    assert adapter.sent == []


async def test_frozen_clock_keeps_message_order() -> None:
    adapter = FakeMessagingAdapter(clock=_FrozenClock())
    first = await adapter.send_text(PHONE, "Uno")
    second = await adapter.send_text(PHONE, "Dos")
    assert first.sent_at < second.sent_at
    messages = await adapter.list_messages(first.conversation_id)
    assert [message.body for message in messages] == ["Uno", "Dos"]
    assert messages[0].direction is MessageDirection.OUTGOING


async def test_template_and_attachment_appear_in_the_conversation_history() -> None:
    adapter = FakeMessagingAdapter()
    receipt = await adapter.send_template(PHONE, "otp_firma", {"code": "1"})
    await adapter.send_attachment(PHONE, b"x", "a.pdf", "application/pdf", None)
    messages = await adapter.list_messages(receipt.conversation_id)
    assert messages[0].body == "[plantilla:otp_firma]"
    assert messages[1].attachment_filename == "a.pdf"
    assert messages[1].body is None


async def test_development_mode_writes_to_the_structured_log_with_masked_phone() -> None:
    adapter = FakeMessagingAdapter(log_messages=True)
    with capture_logs() as logs:
        await adapter.send_text(PHONE, "Hola")
    assert len(logs) == 1
    entry = logs[0]
    assert entry["event"] == "fake_message_sent"
    assert entry["kind"] == "TEXT"
    assert entry["body"] == "Hola"
    assert entry["to"] == "+51999111***"


async def test_list_messages_with_zero_limit_returns_no_messages() -> None:
    adapter = FakeMessagingAdapter()
    sent = await adapter.send_text(PHONE, "Hola")
    assert await adapter.list_messages(sent.conversation_id, limit=0) == ()


async def test_logging_is_off_by_default() -> None:
    adapter = FakeMessagingAdapter()
    with capture_logs() as logs:
        await adapter.send_text(PHONE, "Hola")
    assert logs == []


async def test_status_changes_do_not_require_an_open_window() -> None:
    adapter = FakeMessagingAdapter()
    receipt = await adapter.send_text(PHONE, "Hola")
    adapter.service_window_open = False
    await adapter.set_conversation_status(receipt.conversation_id, ConversationStatus.HUMAN)
    summary = (await adapter.list_conversations())[0]
    assert summary.status is ConversationStatus.HUMAN
    assert summary.service_window_open is False
