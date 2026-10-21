from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from app.domain.entities.outbox_message import OutboxMessage
from app.domain.exceptions.outbox_exceptions import InvalidOutboxStateError
from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.outbox import (
    DEFAULT_RETRY_SCHEDULE,
    DeliveryStatus,
    MessageType,
    OutboxStatus,
)
from tests.domain.outbox_support import (
    DOCUMENT_PAYLOAD,
    NOW,
    PHONE,
    TEXT_PAYLOAD,
    make_message,
)

NAIVE = datetime(2026, 10, 9, 15, 0)
LIMA = timezone(timedelta(hours=-5))


def _sent(**overrides: Any) -> OutboxMessage:
    message = make_message(**overrides)
    message.mark_sent(external_message_id="cw-1", conversation_id=7, now=NOW)
    return message


# --- create ---------------------------------------------------------------------------


def test_create_starts_pending_and_due_now() -> None:
    message = make_message()
    assert message.status is OutboxStatus.PENDING
    assert message.attempts == 0
    assert message.max_attempts == 6
    assert message.next_attempt_at == NOW
    assert message.created_at == NOW
    assert message.delivery_status is None
    assert message.recipient == PHONE


def test_create_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError):
        make_message(now=NAIVE)


def test_create_normalizes_aware_datetimes_to_utc() -> None:
    lima = datetime(2026, 10, 9, 10, 0, tzinfo=LIMA)
    message = make_message(now=lima)
    assert message.next_attempt_at == NOW
    assert message.next_attempt_at.utcoffset() == timedelta(0)


def test_create_rejects_a_recipient_that_is_not_a_phone_number() -> None:
    with pytest.raises(ValidationError):
        make_message(recipient="+51999111222")


@pytest.mark.parametrize("invalid", [0, -1, True, "6"])
def test_create_rejects_invalid_max_attempts(invalid: object) -> None:
    with pytest.raises(ValidationError):
        make_message(max_attempts=invalid)


def test_create_copies_the_payload() -> None:
    payload = {"body": "Hola"}
    message = make_message(payload=payload)
    payload["body"] = "Otro"
    assert message.payload == {"body": "Hola"}


@pytest.mark.parametrize(
    ("message_type", "payload"),
    [
        (MessageType.TEXT, {}),
        (MessageType.TEXT, {"body": "  "}),
        (MessageType.TEXT, {"body": 5}),
        (MessageType.TEMPLATE, {"name": "x"}),
        (MessageType.TEMPLATE, {"name": "x", "params": {"a": 1}}),
        (MessageType.TEMPLATE, {"name": "", "params": {}}),
        (MessageType.INTERACTIVE, {"body": "x", "sections": []}),
        (MessageType.INTERACTIVE, {"body": "x", "sections": [{"title": "t", "rows": []}]}),
        (
            MessageType.INTERACTIVE,
            {"body": "x", "sections": [{"title": "t", "rows": [{"id": "1"}]}]},
        ),
        (MessageType.INTERACTIVE, {"body": "x", "sections": ["no es un objeto"]}),
        (MessageType.INTERACTIVE, {"body": "x", "sections": [{"title": "t", "rows": ["fila"]}]}),
        (MessageType.TEMPLATE, {"name": "x", "params": ["no", "es", "objeto"]}),
        (MessageType.DOCUMENT, {"path": "p", "filename": "f"}),
        (MessageType.DOCUMENT, {"path": "p", "filename": "f", "content_type": "c", "caption": 3}),
    ],
)
def test_create_rejects_a_payload_that_does_not_match_the_message_type(
    message_type: MessageType, payload: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError):
        make_message(message_type=message_type, payload=payload)


def test_create_rejects_a_payload_that_is_not_an_object() -> None:
    with pytest.raises(ValidationError):
        make_message(payload=["body"])  # type: ignore[arg-type]


def test_create_accepts_explicit_null_caption_and_row_description() -> None:
    document = {**DOCUMENT_PAYLOAD, "caption": None}
    assert make_message(message_type=MessageType.DOCUMENT, payload=document).payload == document
    interactive = {
        "body": "Elige",
        "sections": [{"title": "S", "rows": [{"id": "1", "title": "Uno", "description": None}]}],
    }
    assert make_message(message_type=MessageType.INTERACTIVE, payload=interactive).payload


def test_create_accepts_a_document_without_caption_and_empty_template_params() -> None:
    document = {k: v for k, v in DOCUMENT_PAYLOAD.items() if k != "caption"}
    assert make_message(message_type=MessageType.DOCUMENT, payload=document).payload == document
    template = {"name": "aviso", "params": {}}
    assert make_message(message_type=MessageType.TEMPLATE, payload=template).payload == template


# --- mark_sent ------------------------------------------------------------------------


def test_mark_sent_stores_the_chatwoot_identifiers() -> None:
    message = make_message()
    later = NOW + timedelta(seconds=3)
    message.mark_sent(external_message_id="cw-9", conversation_id=42, now=later)
    assert message.status is OutboxStatus.SENT
    assert message.sent_at == later
    assert message.external_message_id == "cw-9"
    assert message.conversation_id == 42
    assert message.payload == TEXT_PAYLOAD


def test_mark_sent_redacts_the_payload_when_requested() -> None:
    message = make_message(redact_after_send=True)
    message.mark_sent(external_message_id="cw-1", conversation_id=1, now=NOW)
    assert message.payload is None


@pytest.mark.parametrize("status", [OutboxStatus.SENT, OutboxStatus.FAILED])
def test_mark_sent_requires_a_pending_message(status: OutboxStatus) -> None:
    message = make_message()
    message.status = status
    with pytest.raises(InvalidOutboxStateError):
        message.mark_sent(external_message_id="cw-1", conversation_id=1, now=NOW)


def test_mark_sent_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError):
        make_message().mark_sent(external_message_id="cw-1", conversation_id=1, now=NAIVE)


@pytest.mark.parametrize("identifier", ["", "   ", "x" * 65])
def test_mark_sent_rejects_an_invalid_external_id(identifier: str) -> None:
    with pytest.raises(ValidationError):
        make_message().mark_sent(external_message_id=identifier, conversation_id=1, now=NOW)


# --- register_failure -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("attempt", "delay"),
    [
        (1, timedelta(seconds=30)),
        (2, timedelta(minutes=2)),
        (3, timedelta(minutes=10)),
        (4, timedelta(minutes=30)),
        (5, timedelta(hours=2)),
    ],
)
def test_transient_failures_back_off_following_the_schedule(attempt: int, delay: timedelta) -> None:
    message = make_message()
    for _ in range(attempt - 1):
        message.register_failure(error="caído", permanent=False, now=NOW)
    failed_at = NOW + timedelta(minutes=1)
    result = message.register_failure(error="caído", permanent=False, now=failed_at)
    assert result is OutboxStatus.PENDING
    assert message.status is OutboxStatus.PENDING
    assert message.attempts == attempt
    assert message.next_attempt_at == failed_at + delay
    assert message.last_error == "caído"


def test_sixth_transient_failure_marks_the_message_failed() -> None:
    message = make_message()
    for _ in range(5):
        message.register_failure(error="caído", permanent=False, now=NOW)
    assert message.status is OutboxStatus.PENDING
    result = message.register_failure(error="caído", permanent=False, now=NOW)
    assert result is OutboxStatus.FAILED
    assert message.status is OutboxStatus.FAILED
    assert message.attempts == 6
    assert DEFAULT_RETRY_SCHEDULE.delay_after(5) == timedelta(hours=2)


def test_permanent_failure_marks_failed_immediately() -> None:
    message = make_message()
    message.register_failure(error="ventana cerrada", permanent=True, now=NOW)
    assert message.status is OutboxStatus.FAILED
    assert message.attempts == 1
    assert message.last_error == "ventana cerrada"


def test_failure_respects_a_custom_max_attempts() -> None:
    message = make_message(max_attempts=2)
    message.register_failure(error="caído", permanent=False, now=NOW)
    assert message.status is OutboxStatus.PENDING
    message.register_failure(error="caído", permanent=False, now=NOW)
    assert message.status is OutboxStatus.FAILED


def test_failure_clips_long_errors_and_names_empty_ones() -> None:
    message = make_message()
    message.register_failure(error="e" * 900, permanent=False, now=NOW)
    assert message.last_error == "e" * 500
    message.register_failure(error="   ", permanent=False, now=NOW)
    assert message.last_error == "Error desconocido"


@pytest.mark.parametrize("status", [OutboxStatus.SENT, OutboxStatus.FAILED])
def test_register_failure_requires_a_pending_message(status: OutboxStatus) -> None:
    message = make_message()
    message.status = status
    with pytest.raises(InvalidOutboxStateError):
        message.register_failure(error="x", permanent=False, now=NOW)


def test_register_failure_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError):
        make_message().register_failure(error="x", permanent=False, now=NAIVE)


# --- record_delivery ------------------------------------------------------------------


def test_record_delivery_requires_a_sent_message() -> None:
    with pytest.raises(InvalidOutboxStateError):
        make_message().record_delivery(status=DeliveryStatus.DELIVERED, error=None, at=NOW)


def test_delivered_then_read_keeps_both_timestamps() -> None:
    message = _sent()
    delivered_at = NOW + timedelta(seconds=5)
    read_at = NOW + timedelta(minutes=2)
    assert message.record_delivery(status=DeliveryStatus.DELIVERED, error=None, at=delivered_at)
    assert message.record_delivery(status=DeliveryStatus.READ, error=None, at=read_at)
    assert message.delivery_status is DeliveryStatus.READ
    assert message.delivered_at == delivered_at
    assert message.read_at == read_at


def test_read_without_a_previous_delivered_also_sets_delivered_at() -> None:
    message = _sent()
    message.record_delivery(status=DeliveryStatus.READ, error=None, at=NOW)
    assert message.delivered_at == NOW
    assert message.read_at == NOW


def test_delivered_after_read_is_ignored() -> None:
    message = _sent()
    message.record_delivery(status=DeliveryStatus.READ, error=None, at=NOW)
    later = NOW + timedelta(minutes=1)
    assert message.record_delivery(status=DeliveryStatus.DELIVERED, error=None, at=later) is False
    assert message.delivery_status is DeliveryStatus.READ
    assert message.delivered_at == NOW


@pytest.mark.parametrize("settled", [DeliveryStatus.DELIVERED, DeliveryStatus.READ])
def test_failed_never_overwrites_delivered_or_read(settled: DeliveryStatus) -> None:
    message = _sent()
    message.record_delivery(status=settled, error=None, at=NOW)
    assert message.record_delivery(status=DeliveryStatus.FAILED, error="x", at=NOW) is False
    assert message.delivery_status is settled
    assert message.delivery_error is None


def test_failed_records_the_reason() -> None:
    message = _sent()
    assert message.record_delivery(status=DeliveryStatus.FAILED, error="Fuera de ventana", at=NOW)
    assert message.delivery_status is DeliveryStatus.FAILED
    assert message.delivery_error == "Fuera de ventana"


def test_failed_without_a_reason_keeps_the_error_empty() -> None:
    message = _sent()
    assert message.record_delivery(status=DeliveryStatus.FAILED, error=None, at=NOW)
    assert message.delivery_status is DeliveryStatus.FAILED
    assert message.delivery_error is None


def test_delivered_after_failed_clears_the_error() -> None:
    message = _sent()
    message.record_delivery(status=DeliveryStatus.FAILED, error="Fuera de ventana", at=NOW)
    message.record_delivery(status=DeliveryStatus.DELIVERED, error=None, at=NOW)
    assert message.delivery_status is DeliveryStatus.DELIVERED
    assert message.delivery_error is None


def test_repeated_read_is_ignored() -> None:
    message = _sent()
    message.record_delivery(status=DeliveryStatus.READ, error=None, at=NOW)
    later = NOW + timedelta(minutes=1)
    assert message.record_delivery(status=DeliveryStatus.READ, error=None, at=later) is False
    assert message.read_at == NOW


def test_repeated_delivered_is_ignored() -> None:
    message = _sent()
    message.record_delivery(status=DeliveryStatus.DELIVERED, error=None, at=NOW)
    later = NOW + timedelta(minutes=1)
    assert message.record_delivery(status=DeliveryStatus.DELIVERED, error=None, at=later) is False
    assert message.delivered_at == NOW


def test_record_delivery_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError):
        _sent().record_delivery(status=DeliveryStatus.DELIVERED, error=None, at=NAIVE)


# --- retry ----------------------------------------------------------------------------


def test_retry_requeues_a_message_whose_send_failed() -> None:
    message = make_message()
    message.register_failure(error="ventana cerrada", permanent=True, now=NOW)
    later = NOW + timedelta(hours=1)
    message.retry(now=later)
    assert message.status is OutboxStatus.PENDING
    assert message.attempts == 0
    assert message.next_attempt_at == later
    assert message.last_error is None


def test_retry_requeues_a_message_rejected_by_whatsapp_and_clears_delivery_data() -> None:
    message = _sent()
    message.record_delivery(status=DeliveryStatus.FAILED, error="Sin WhatsApp", at=NOW)
    later = NOW + timedelta(hours=1)
    message.retry(now=later)
    assert message.status is OutboxStatus.PENDING
    assert message.next_attempt_at == later
    assert message.delivery_status is None
    assert message.delivery_error is None
    assert message.delivered_at is None
    assert message.read_at is None
    assert message.external_message_id is None
    assert message.conversation_id is None
    assert message.sent_at is None


@pytest.mark.parametrize("delivery", [None, DeliveryStatus.DELIVERED, DeliveryStatus.READ])
def test_retry_rejects_a_healthy_sent_message(delivery: DeliveryStatus | None) -> None:
    message = _sent()
    if delivery is not None:
        message.record_delivery(status=delivery, error=None, at=NOW)
    with pytest.raises(InvalidOutboxStateError):
        message.retry(now=NOW)


def test_retry_rejects_a_pending_message() -> None:
    with pytest.raises(InvalidOutboxStateError):
        make_message().retry(now=NOW)


def test_retry_rejects_a_redacted_message() -> None:
    message = _sent(redact_after_send=True)
    message.record_delivery(status=DeliveryStatus.FAILED, error="Sin WhatsApp", at=NOW)
    with pytest.raises(InvalidOutboxStateError):
        message.retry(now=NOW)
    assert message.delivery_status is DeliveryStatus.FAILED


def test_retry_rejects_naive_datetime() -> None:
    message = make_message()
    message.register_failure(error="x", permanent=True, now=NOW)
    with pytest.raises(ValidationError):
        message.retry(now=NAIVE)


def test_each_message_gets_its_own_identifier() -> None:
    assert make_message().id != make_message().id


def test_retry_keeps_the_previous_external_id_to_preserve_authorship() -> None:
    message = _sent()
    message.record_delivery(status=DeliveryStatus.FAILED, error="Sin WhatsApp", at=NOW)
    message.retry(now=NOW)
    assert message.external_message_id is None
    assert message.retried_external_message_id == "cw-1"


def test_a_second_retry_without_a_new_send_does_not_lose_the_kept_id() -> None:
    message = _sent()
    message.record_delivery(status=DeliveryStatus.FAILED, error="Sin WhatsApp", at=NOW)
    message.retry(now=NOW)
    message.register_failure(error="caído", permanent=True, now=NOW)
    message.retry(now=NOW)
    assert message.retried_external_message_id == "cw-1"


def test_is_retryable_matches_the_retry_rules() -> None:
    failed = make_message()
    failed.register_failure(error="x", permanent=True, now=NOW)
    rejected = _sent()
    rejected.record_delivery(status=DeliveryStatus.FAILED, error="x", at=NOW)
    redacted = _sent(redact_after_send=True)
    redacted.record_delivery(status=DeliveryStatus.FAILED, error="x", at=NOW)
    assert failed.is_retryable
    assert rejected.is_retryable
    assert not _sent().is_retryable
    assert not make_message().is_retryable
    assert not redacted.is_retryable
