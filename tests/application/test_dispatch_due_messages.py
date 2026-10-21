from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any

import pytest
from structlog.testing import capture_logs

from app.application.dtos.messaging_dto import MessageReceipt
from app.application.ports.output.outbox_repository_port import IOutboxRepositoryPort
from app.application.use_cases.messaging.dispatch_due_messages import (
    DispatchDueMessages,
    DispatchSummary,
)
from app.domain.entities.outbox_message import OutboxMessage
from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.outbox import MessageType, OutboxStatus
from app.domain.value_objects.phone_number import PhoneNumber
from app.infrastructure.adapters.secondary.external_services.fake_messaging_adapter import (
    FakeMessagingAdapter,
    SentMessageKind,
)
from tests.application.outbox_support import FakeDocumentSource, FixedClock, InMemoryOutboxStore
from tests.domain.outbox_support import NOW, PHONE, make_message

SECRET_BODY = "Tu código es 481516"


class ExplodingMessaging(FakeMessagingAdapter):
    """Falla con un error inesperado que repite el contenido del mensaje."""

    async def send_text(self, to: PhoneNumber, body: str) -> MessageReceipt:
        raise RuntimeError(f"Gateway rechazó el cuerpo: {body}")


class SelectiveMessaging(FakeMessagingAdapter):
    """Falla solo para los textos que contienen ``falla``."""

    async def send_text(self, to: PhoneNumber, body: str) -> MessageReceipt:
        if "falla" in body:
            raise RuntimeError("Error inesperado")
        return await super().send_text(to, body)


def _build(
    store: InMemoryOutboxStore,
    *,
    messaging: FakeMessagingAdapter | None = None,
    documents: FakeDocumentSource | None = None,
    clock: FixedClock | None = None,
    batch_size: int = 20,
    lease_seconds: int = 60,
) -> DispatchDueMessages:
    return DispatchDueMessages(
        transaction=store.transaction,
        messaging=messaging or FakeMessagingAdapter(clock=clock or FixedClock()),
        documents=documents or FakeDocumentSource(),
        clock=clock or FixedClock(),
        batch_size=batch_size,
        lease_seconds=lease_seconds,
    )


def _text(body: str = "Hola", **overrides: Any) -> OutboxMessage:
    return make_message(payload={"body": body}, **overrides)


# --- entrega por tipo ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("message_type", "kind"),
    [
        (MessageType.TEXT, SentMessageKind.TEXT),
        (MessageType.TEMPLATE, SentMessageKind.TEMPLATE),
        (MessageType.INTERACTIVE, SentMessageKind.INTERACTIVE_LIST),
    ],
)
async def test_dispatch_uses_the_gateway_method_matching_the_type(
    message_type: MessageType, kind: SentMessageKind
) -> None:
    store = InMemoryOutboxStore()
    message = store.put(make_message(message_type=message_type))
    messaging = FakeMessagingAdapter()

    summary = await _build(store, messaging=messaging).execute()

    assert summary == DispatchSummary(claimed=1, sent=1)
    assert [sent.kind for sent in messaging.sent] == [kind]
    assert messaging.sent[0].to == PHONE
    assert store.messages[message.id].status is OutboxStatus.SENT


async def test_dispatch_reads_the_document_and_sends_it_as_an_attachment() -> None:
    store = InMemoryOutboxStore()
    message = store.put(make_message(message_type=MessageType.DOCUMENT))
    documents = FakeDocumentSource({"database/contracts/abc": b"%PDF-1.4 contenido"})
    messaging = FakeMessagingAdapter()

    summary = await _build(store, messaging=messaging, documents=documents).execute()

    assert summary.sent == 1
    assert documents.reads == ["database/contracts/abc"]
    sent = messaging.sent[0]
    assert sent.kind is SentMessageKind.ATTACHMENT
    assert sent.filename == "contrato.pdf"
    assert sent.content_type == "application/pdf"
    assert sent.size_bytes == len(b"%PDF-1.4 contenido")
    assert sent.body == "Tu contrato"
    assert store.messages[message.id].payload is not None  # sin redacción, la ruta se conserva


async def test_successful_dispatch_stores_the_chatwoot_identifiers() -> None:
    store = InMemoryOutboxStore()
    message = store.put(_text())
    clock = FixedClock()

    await _build(store, clock=clock).execute()

    stored = store.messages[message.id]
    assert stored.status is OutboxStatus.SENT
    assert stored.sent_at == NOW
    assert stored.external_message_id == "1"
    assert stored.conversation_id == 1
    assert stored.attempts == 0


async def test_otp_payload_is_redacted_once_sent() -> None:
    store = InMemoryOutboxStore()
    message = store.put(_text(SECRET_BODY, redact_after_send=True))

    await _build(store).execute()

    stored = store.messages[message.id]
    assert stored.status is OutboxStatus.SENT
    assert stored.payload is None


# --- selección del lote ------------------------------------------------------------------


async def test_dispatch_with_nothing_due_is_a_cheap_noop() -> None:
    store = InMemoryOutboxStore()
    store.put(_text(now=NOW + timedelta(minutes=5)))

    summary = await _build(store).execute()

    assert summary == DispatchSummary()
    assert store.commits == 1  # solo la transacción de reserva


async def test_dispatch_skips_messages_that_are_not_pending() -> None:
    store = InMemoryOutboxStore()
    sent = store.put(_text())
    sent.mark_sent(external_message_id="cw-1", conversation_id=1, now=NOW)
    store.put(sent)
    failed = store.put(_text())
    failed.register_failure(error="x", permanent=True, now=NOW)
    store.put(failed)
    messaging = FakeMessagingAdapter()

    summary = await _build(store, messaging=messaging).execute()

    assert summary.claimed == 0
    assert messaging.sent == []


async def test_dispatch_respects_the_batch_size_oldest_first() -> None:
    store = InMemoryOutboxStore()
    newest = store.put(_text("tercero", now=NOW - timedelta(minutes=1)))
    oldest = store.put(_text("primero", now=NOW - timedelta(minutes=30)))
    middle = store.put(_text("segundo", now=NOW - timedelta(minutes=10)))
    messaging = FakeMessagingAdapter()

    summary = await _build(store, messaging=messaging, batch_size=2).execute()

    assert summary.claimed == 2
    assert [sent.body for sent in messaging.sent] == ["primero", "segundo"]
    assert store.messages[oldest.id].status is OutboxStatus.SENT
    assert store.messages[middle.id].status is OutboxStatus.SENT
    assert store.messages[newest.id].status is OutboxStatus.PENDING


async def test_each_result_is_saved_in_its_own_transaction() -> None:
    store = InMemoryOutboxStore()
    for index in range(3):
        store.put(_text(f"mensaje {index}"))

    await _build(store).execute()

    assert store.commits == 1 + 3


# --- caída del gateway y reintentos --------------------------------------------------------


async def test_gateway_down_reschedules_the_message_with_backoff() -> None:
    store = InMemoryOutboxStore()
    message = store.put(_text())
    messaging = FakeMessagingAdapter()
    messaging.unavailable = True

    summary = await _build(store, messaging=messaging).execute()

    stored = store.messages[message.id]
    assert summary == DispatchSummary(claimed=1, rescheduled=1)
    assert stored.status is OutboxStatus.PENDING
    assert stored.attempts == 1
    assert stored.next_attempt_at == NOW + timedelta(seconds=30)
    assert stored.last_error is not None
    assert "MessagingUnavailableError" in stored.last_error


async def test_a_long_outage_follows_the_full_backoff_and_ends_failed() -> None:
    store = InMemoryOutboxStore()
    message = store.put(_text())
    clock = FixedClock()
    messaging = FakeMessagingAdapter(clock=clock)
    messaging.unavailable = True
    dispatcher = _build(store, messaging=messaging, clock=clock)
    waits: list[timedelta] = []

    for _ in range(6):
        await dispatcher.execute()
        stored = store.messages[message.id]
        if stored.status is OutboxStatus.FAILED:
            break
        waits.append(stored.next_attempt_at - clock.now)
        clock.now = stored.next_attempt_at

    assert waits == [
        timedelta(seconds=30),
        timedelta(minutes=2),
        timedelta(minutes=10),
        timedelta(minutes=30),
        timedelta(hours=2),
    ]
    assert store.messages[message.id].status is OutboxStatus.FAILED
    assert store.messages[message.id].attempts == 6
    assert (await dispatcher.execute()).claimed == 0


async def test_recovered_gateway_delivers_a_message_that_had_failed_before() -> None:
    store = InMemoryOutboxStore()
    message = store.put(_text())
    clock = FixedClock()
    messaging = FakeMessagingAdapter(clock=clock)
    dispatcher = _build(store, messaging=messaging, clock=clock)
    messaging.unavailable = True
    await dispatcher.execute()
    messaging.unavailable = False
    clock.advance(timedelta(seconds=31))

    summary = await dispatcher.execute()

    assert summary.sent == 1
    assert store.messages[message.id].status is OutboxStatus.SENT
    assert store.messages[message.id].attempts == 1


async def test_closed_service_window_fails_immediately_without_retries() -> None:
    store = InMemoryOutboxStore()
    message = store.put(_text())
    messaging = FakeMessagingAdapter()
    messaging.service_window_open = False

    summary = await _build(store, messaging=messaging).execute()

    stored = store.messages[message.id]
    assert summary == DispatchSummary(claimed=1, failed=1)
    assert stored.status is OutboxStatus.FAILED
    assert stored.attempts == 1
    assert stored.last_error is not None
    assert "ServiceWindowClosedError" in stored.last_error


async def test_unexpected_errors_are_transient_and_never_expose_the_payload() -> None:
    store = InMemoryOutboxStore()
    message = store.put(_text(SECRET_BODY, redact_after_send=True))

    with capture_logs() as logs:
        summary = await _build(store, messaging=ExplodingMessaging()).execute()

    stored = store.messages[message.id]
    assert summary == DispatchSummary(claimed=1, rescheduled=1)
    assert stored.status is OutboxStatus.PENDING
    assert stored.last_error == "RuntimeError"
    assert "481516" not in repr(logs)
    assert any(entry["event"] == "outbox_message_rescheduled" for entry in logs)


async def test_logs_of_a_successful_dispatch_do_not_include_the_payload() -> None:
    store = InMemoryOutboxStore()
    store.put(_text(SECRET_BODY))

    with capture_logs() as logs:
        await _build(store).execute()

    assert [entry["event"] for entry in logs] == ["outbox_message_sent"]
    assert "481516" not in repr(logs)


async def test_unreadable_document_is_transient_and_skips_the_gateway() -> None:
    store = InMemoryOutboxStore()
    message = store.put(make_message(message_type=MessageType.DOCUMENT))
    messaging = FakeMessagingAdapter()

    summary = await _build(store, messaging=messaging).execute()

    stored = store.messages[message.id]
    assert summary.rescheduled == 1
    assert messaging.sent == []
    assert stored.last_error is not None
    assert "ResourceNotFoundError" in stored.last_error


async def test_a_pending_message_without_payload_fails_permanently() -> None:
    store = InMemoryOutboxStore()
    message = _text()
    message.payload = None
    store.put(message)
    messaging = FakeMessagingAdapter()

    summary = await _build(store, messaging=messaging).execute()

    assert summary.failed == 1
    assert messaging.sent == []
    assert store.messages[message.id].status is OutboxStatus.FAILED


# --- aislamiento entre mensajes ------------------------------------------------------------


async def test_one_failing_message_does_not_affect_the_others() -> None:
    store = InMemoryOutboxStore()
    first = store.put(_text("uno", now=NOW - timedelta(minutes=3)))
    bad = store.put(_text("falla", now=NOW - timedelta(minutes=2)))
    last = store.put(_text("tres", now=NOW - timedelta(minutes=1)))

    summary = await _build(store, messaging=SelectiveMessaging()).execute()

    assert summary == DispatchSummary(claimed=3, sent=2, rescheduled=1)
    assert store.messages[first.id].status is OutboxStatus.SENT
    assert store.messages[last.id].status is OutboxStatus.SENT
    assert store.messages[bad.id].status is OutboxStatus.PENDING
    assert store.messages[bad.id].attempts == 1


async def test_a_persistence_error_on_one_message_does_not_stop_the_batch() -> None:
    store = InMemoryOutboxStore()
    first = store.put(_text("uno", now=NOW - timedelta(minutes=2)))
    broken = store.put(_text("dos", now=NOW - timedelta(minutes=1)))
    store.fail_save.add(first.id)

    summary = await _build(store).execute()

    assert summary == DispatchSummary(claimed=2, sent=1, errors=1)
    assert store.messages[broken.id].status is OutboxStatus.SENT
    assert store.messages[first.id].status is OutboxStatus.PENDING
    assert store.rollbacks == 1


async def test_a_message_whose_result_was_not_saved_stays_leased_then_is_retried() -> None:
    store = InMemoryOutboxStore()
    clock = FixedClock()
    message = store.put(_text())
    store.fail_save.add(message.id)
    messaging = FakeMessagingAdapter(clock=clock)
    dispatcher = _build(store, messaging=messaging, clock=clock, lease_seconds=60)

    await dispatcher.execute()
    assert len(messaging.sent) == 1
    assert store.messages[message.id].next_attempt_at == NOW + timedelta(seconds=60)

    store.fail_save.clear()
    clock.advance(timedelta(seconds=59))
    assert (await dispatcher.execute()).claimed == 0  # la reserva sigue vigente

    clock.advance(timedelta(seconds=2))
    summary = await dispatcher.execute()  # la reserva venció: entrega al menos una vez
    assert summary.sent == 1
    assert len(messaging.sent) == 2
    assert store.messages[message.id].status is OutboxStatus.SENT


async def test_a_late_result_for_a_message_already_resolved_is_discarded() -> None:
    store = InMemoryOutboxStore()
    message = store.put(_text())

    class RacingMessaging(FakeMessagingAdapter):
        async def send_text(self, to: PhoneNumber, body: str) -> MessageReceipt:
            receipt = await super().send_text(to, body)
            # Otro worker, con la reserva vencida, ya guardó su propio resultado.
            other = store.messages[message.id]
            other.mark_sent(external_message_id="cw-other", conversation_id=9, now=NOW)
            return receipt

    with capture_logs() as logs:
        summary = await _build(store, messaging=RacingMessaging()).execute()

    stored = store.messages[message.id]
    assert summary == DispatchSummary(claimed=1, discarded=1)
    assert stored.external_message_id == "cw-other"
    assert stored.conversation_id == 9
    assert [entry["event"] for entry in logs] == ["outbox_result_discarded"]


async def test_a_claim_failure_aborts_the_cycle() -> None:
    store = InMemoryOutboxStore()
    store.put(_text())
    messaging = FakeMessagingAdapter()

    class BrokenClaim:
        async def claim_due(self, **_: Any) -> Sequence[OutboxMessage]:
            raise ConnectionError("base de datos caída")

    @asynccontextmanager
    async def broken_transaction() -> AsyncIterator[IOutboxRepositoryPort]:
        yield BrokenClaim()  # type: ignore[misc]

    dispatcher = DispatchDueMessages(
        transaction=broken_transaction,
        messaging=messaging,
        documents=FakeDocumentSource(),
        clock=FixedClock(),
        batch_size=20,
        lease_seconds=60,
    )
    with pytest.raises(ConnectionError):
        await dispatcher.execute()
    assert messaging.sent == []


@pytest.mark.parametrize(("batch_size", "lease_seconds"), [(0, 60), (20, 0), (-1, -1)])
def test_constructor_rejects_non_positive_batch_and_lease(
    batch_size: int, lease_seconds: int
) -> None:
    with pytest.raises(ValidationError):
        _build(InMemoryOutboxStore(), batch_size=batch_size, lease_seconds=lease_seconds)
