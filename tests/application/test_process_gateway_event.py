"""ProcessGatewayEvent: enruta los eventos del gateway y registra los avisos de entrega."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta, timezone

import pytest
from structlog.testing import capture_logs

from app.application.dtos.gateway_event_dto import (
    DeliveryNotice,
    DeliveryReport,
    GatewayEvent,
    GatewayEventOutcome,
    UnhandledGatewayEvent,
)
from app.application.dtos.messaging_dto import MessageDirection
from app.application.ports.output.outbox_repository_port import IOutboxRepositoryPort
from app.application.use_cases.messaging.process_gateway_event import ProcessGatewayEvent
from app.domain.entities.outbox_message import OutboxMessage
from app.domain.exceptions.messaging_exceptions import MessagingUnavailableError
from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.outbox import DeliveryStatus, OutboxStatus
from tests.application.outbox_support import InMemoryOutboxStore
from tests.domain.outbox_support import NOW, make_message

RAW_BODY = b'{"event": "message_updated"}'
EXTERNAL_ID = "4821"
CONVERSATION_ID = 57
RECEIVED_AT = NOW + timedelta(seconds=30)
UPDATED_AT = NOW + timedelta(seconds=10)
# Campos que un log de este caso de uso puede llevar (DSR-7): nada de contenido ni teléfonos.
ALLOWED_LOG_KEYS = {
    "event",
    "log_level",
    "kind",
    "direction",
    "conversation_id",
    "external_message_id",
    "delivery_status",
    "reason",
}


class _Transactions:
    """Fábrica de transacciones que informa cuántas están abiertas en cada momento."""

    def __init__(self, store: InMemoryOutboxStore) -> None:
        self._store = store
        self.open = 0

    @asynccontextmanager
    async def __call__(self) -> AsyncIterator[IOutboxRepositoryPort]:
        async with self._store.transaction() as repository:
            self.open += 1
            try:
                yield repository
            finally:
                self.open -= 1


class _FakeGatewayEvents:
    """Doble de ``IGatewayEventPort``: entrega un evento fijo y registra las consultas."""

    def __init__(
        self,
        transactions: _Transactions,
        *,
        event: GatewayEvent | None = None,
        parse_error: Exception | None = None,
        report: DeliveryReport | None = None,
        lookup_error: Exception | None = None,
    ) -> None:
        self._transactions = transactions
        self._event = event
        self._parse_error = parse_error
        self._report = report
        self._lookup_error = lookup_error
        self.parsed: list[bytes] = []
        self.lookups: list[tuple[int, str]] = []
        self.open_transactions_at_lookup: list[int] = []

    def parse_event(self, raw_body: bytes) -> GatewayEvent:
        self.parsed.append(raw_body)
        if self._parse_error is not None:
            raise self._parse_error
        assert self._event is not None
        return self._event

    async def get_delivery_status(
        self, conversation_id: int, external_message_id: str
    ) -> DeliveryReport | None:
        self.lookups.append((conversation_id, external_message_id))
        self.open_transactions_at_lookup.append(self._transactions.open)
        if self._lookup_error is not None:
            raise self._lookup_error
        return self._report


def _sent_message(external_id: str = EXTERNAL_ID) -> OutboxMessage:
    message = make_message()
    message.mark_sent(external_message_id=external_id, conversation_id=CONVERSATION_ID, now=NOW)
    return message


def _notice(**overrides: object) -> DeliveryNotice:
    values: dict[str, object] = {
        "external_message_id": EXTERNAL_ID,
        "conversation_id": CONVERSATION_ID,
        "status": DeliveryStatus.DELIVERED,
        "error": None,
    }
    values.update(overrides)
    return DeliveryNotice(**values)  # type: ignore[arg-type]


def _build(
    event: GatewayEvent | None = None,
    *,
    message: OutboxMessage | None = None,
    **gateway_options: object,
) -> tuple[ProcessGatewayEvent, InMemoryOutboxStore, _FakeGatewayEvents]:
    store = InMemoryOutboxStore()
    if message is not None:
        store.put(message)
    transactions = _Transactions(store)
    gateway = _FakeGatewayEvents(transactions, event=event, **gateway_options)  # type: ignore[arg-type]
    return ProcessGatewayEvent(transaction=transactions, gateway=gateway), store, gateway


def _stored(store: InMemoryOutboxStore) -> OutboxMessage:
    (message,) = store.messages.values()
    return message


# --- Estado presente en el aviso: no hay consulta ------------------------------------------


@pytest.mark.parametrize("status", [DeliveryStatus.DELIVERED, DeliveryStatus.READ])
async def test_a_delivered_or_read_notice_is_recorded_without_any_lookup(
    status: DeliveryStatus,
) -> None:
    use_case, store, gateway = _build(_notice(status=status), message=_sent_message())

    outcome = await use_case.execute(raw_body=RAW_BODY, received_at=RECEIVED_AT)

    assert outcome is GatewayEventOutcome.APPLIED
    assert _stored(store).delivery_status is status
    assert gateway.parsed == [RAW_BODY]
    assert gateway.lookups == []


async def test_a_failed_notice_keeps_the_external_error_text() -> None:
    notice = _notice(status=DeliveryStatus.FAILED, error="message_outside_messaging_window")
    use_case, store, _ = _build(notice, message=_sent_message())

    outcome = await use_case.execute(raw_body=RAW_BODY, received_at=RECEIVED_AT)

    assert outcome is GatewayEventOutcome.APPLIED
    assert _stored(store).delivery_status is DeliveryStatus.FAILED
    assert _stored(store).delivery_error == "message_outside_messaging_window"


async def test_a_failed_notice_without_error_text_is_recorded_with_no_error() -> None:
    use_case, store, _ = _build(_notice(status=DeliveryStatus.FAILED), message=_sent_message())

    await use_case.execute(raw_body=RAW_BODY, received_at=RECEIVED_AT)

    assert _stored(store).delivery_status is DeliveryStatus.FAILED
    assert _stored(store).delivery_error is None


async def test_a_non_failed_notice_never_carries_an_error_to_the_record() -> None:
    notice = _notice(status=DeliveryStatus.READ, error="texto que no corresponde")
    use_case, store, _ = _build(notice, message=_sent_message())

    await use_case.execute(raw_body=RAW_BODY, received_at=RECEIVED_AT)

    assert _stored(store).delivery_status is DeliveryStatus.READ
    assert _stored(store).delivery_error is None


# --- Estado ausente: una consulta fuera de toda transacción --------------------------------


async def test_an_absent_status_is_fetched_once_outside_any_transaction() -> None:
    use_case, store, gateway = _build(
        _notice(status=None),
        message=_sent_message(),
        report=DeliveryReport(status=DeliveryStatus.READ, error=None),
    )

    outcome = await use_case.execute(raw_body=RAW_BODY, received_at=RECEIVED_AT)

    assert outcome is GatewayEventOutcome.APPLIED
    assert _stored(store).delivery_status is DeliveryStatus.READ
    assert gateway.lookups == [(CONVERSATION_ID, EXTERNAL_ID)]
    assert gateway.open_transactions_at_lookup == [0]


async def test_a_fetched_failure_uses_the_error_text_of_the_fetched_message() -> None:
    use_case, store, _ = _build(
        _notice(status=None),
        message=_sent_message(),
        report=DeliveryReport(status=DeliveryStatus.FAILED, error="fetched_reason"),
    )

    await use_case.execute(raw_body=RAW_BODY, received_at=RECEIVED_AT)

    assert _stored(store).delivery_error == "fetched_reason"


async def test_the_error_text_of_the_payload_wins_over_the_fetched_one() -> None:
    use_case, store, _ = _build(
        _notice(status=None, error="payload_reason"),
        message=_sent_message(),
        report=DeliveryReport(status=DeliveryStatus.FAILED, error="fetched_reason"),
    )

    await use_case.execute(raw_body=RAW_BODY, received_at=RECEIVED_AT)

    assert _stored(store).delivery_error == "payload_reason"


@pytest.mark.parametrize(
    "report", [None, DeliveryReport(status=None, error=None)], ids=["not-found", "sent"]
)
async def test_a_status_that_cannot_be_resolved_changes_nothing(
    report: DeliveryReport | None,
) -> None:
    use_case, store, gateway = _build(_notice(status=None), message=_sent_message(), report=report)

    outcome = await use_case.execute(raw_body=RAW_BODY, received_at=RECEIVED_AT)

    assert outcome is GatewayEventOutcome.UNRESOLVED
    assert len(gateway.lookups) == 1
    assert _stored(store).delivery_status is None


async def test_a_payload_status_that_is_not_recordable_is_unresolved_without_lookup() -> None:
    # Un `status: "sent"` en el payload no se registra y tampoco justifica consultar la API.
    use_case, store, gateway = _build(
        _notice(status=None, status_in_payload=True), message=_sent_message()
    )

    outcome = await use_case.execute(raw_body=RAW_BODY, received_at=RECEIVED_AT)

    assert outcome is GatewayEventOutcome.UNRESOLVED
    assert gateway.lookups == []
    assert _stored(store).delivery_status is None


async def test_an_absent_status_without_conversation_cannot_be_fetched() -> None:
    use_case, _, gateway = _build(
        _notice(status=None, conversation_id=None), message=_sent_message()
    )

    outcome = await use_case.execute(raw_body=RAW_BODY, received_at=RECEIVED_AT)

    assert outcome is GatewayEventOutcome.UNRESOLVED
    assert gateway.lookups == []


async def test_a_failing_lookup_propagates_and_records_nothing() -> None:
    use_case, store, _ = _build(
        _notice(status=None),
        message=_sent_message(),
        lookup_error=MessagingUnavailableError("Chatwoot respondió 503 en get_delivery_status"),
    )

    with pytest.raises(MessagingUnavailableError):
        await use_case.execute(raw_body=RAW_BODY, received_at=RECEIVED_AT)

    assert _stored(store).delivery_status is None


# --- Mensaje desconocido ------------------------------------------------------------------


async def test_an_unknown_message_is_reported_before_any_lookup() -> None:
    use_case, store, gateway = _build(
        _notice(status=None), message=_sent_message("otro-id"), report=None
    )

    outcome = await use_case.execute(raw_body=RAW_BODY, received_at=RECEIVED_AT)

    assert outcome is GatewayEventOutcome.UNKNOWN_MESSAGE
    assert gateway.lookups == []
    assert _stored(store).delivery_status is None


async def test_the_last_attempt_logs_the_unmatched_notice_with_ids_only() -> None:
    use_case, _, _ = _build(_notice(status=DeliveryStatus.READ))

    with capture_logs() as logs:
        outcome = await use_case.execute(
            raw_body=RAW_BODY, received_at=RECEIVED_AT, last_attempt=True
        )

    assert outcome is GatewayEventOutcome.UNKNOWN_MESSAGE
    assert [entry["event"] for entry in logs] == ["delivery_notice_unmatched"]
    assert logs[0]["external_message_id"] == EXTERNAL_ID
    assert logs[0]["delivery_status"] == "READ"


async def test_an_earlier_attempt_does_not_log_the_unmatched_notice() -> None:
    use_case, _, _ = _build(_notice())

    with capture_logs() as logs:
        await use_case.execute(raw_body=RAW_BODY, received_at=RECEIVED_AT)

    assert logs == []


# --- Resultado de RecordDeliveryStatus ----------------------------------------------------


async def test_a_stale_notice_is_ignored_without_requesting_a_retry() -> None:
    message = _sent_message()
    message.record_delivery(status=DeliveryStatus.READ, error=None, at=NOW)
    use_case, store, _ = _build(_notice(status=DeliveryStatus.DELIVERED), message=message)

    outcome = await use_case.execute(raw_body=RAW_BODY, received_at=RECEIVED_AT)

    assert outcome is GatewayEventOutcome.IGNORED
    assert _stored(store).delivery_status is DeliveryStatus.READ


async def test_a_message_that_is_not_sent_is_ignored_and_logged() -> None:
    message = _sent_message()
    message.status = OutboxStatus.FAILED
    use_case, store, _ = _build(_notice(), message=message)

    with capture_logs() as logs:
        outcome = await use_case.execute(raw_body=RAW_BODY, received_at=RECEIVED_AT)

    assert outcome is GatewayEventOutcome.IGNORED
    assert [entry["event"] for entry in logs] == ["delivery_notice_invalid_state"]
    assert logs[0]["external_message_id"] == EXTERNAL_ID
    assert _stored(store).delivery_status is None


# --- Valor de ``at`` ----------------------------------------------------------------------


async def test_at_is_the_update_time_of_the_payload_when_it_exists() -> None:
    use_case, store, _ = _build(_notice(updated_at=UPDATED_AT), message=_sent_message())

    await use_case.execute(raw_body=RAW_BODY, received_at=RECEIVED_AT)

    assert _stored(store).delivered_at == UPDATED_AT


async def test_at_falls_back_to_the_receive_time_carried_in_the_job() -> None:
    use_case, store, _ = _build(_notice(updated_at=None), message=_sent_message())

    await use_case.execute(raw_body=RAW_BODY, received_at=RECEIVED_AT)

    assert _stored(store).delivered_at == RECEIVED_AT


async def test_at_is_converted_to_utc() -> None:
    lima = timezone(timedelta(hours=-5))
    local = UPDATED_AT.astimezone(lima)
    use_case, store, _ = _build(_notice(updated_at=local), message=_sent_message())

    await use_case.execute(raw_body=RAW_BODY, received_at=RECEIVED_AT)

    delivered_at = _stored(store).delivered_at
    assert delivered_at == UPDATED_AT
    assert delivered_at is not None and delivered_at.utcoffset() == timedelta(0)
    assert delivered_at.tzinfo is UTC


async def test_a_naive_update_time_is_read_as_utc() -> None:
    naive = datetime(2026, 10, 9, 15, 0, 10)
    use_case, store, _ = _build(_notice(updated_at=naive), message=_sent_message())

    await use_case.execute(raw_body=RAW_BODY, received_at=RECEIVED_AT)

    assert _stored(store).delivered_at == naive.replace(tzinfo=UTC)


# --- Cuerpo no reconocible y eventos que no son avisos de entrega -------------------------


async def test_a_malformed_body_is_logged_and_dropped() -> None:
    use_case, store, gateway = _build(parse_error=ValidationError("Cuerpo inválido"))

    with capture_logs() as logs:
        outcome = await use_case.execute(raw_body=b"no es json", received_at=RECEIVED_AT)

    assert outcome is GatewayEventOutcome.MALFORMED
    assert gateway.parsed == [b"no es json"]
    assert [entry["event"] for entry in logs] == ["gateway_event_malformed"]
    assert (store.commits, store.rollbacks) == (0, 0)


@pytest.mark.parametrize(
    "event",
    [
        UnhandledGatewayEvent(
            kind="message_created",
            direction=MessageDirection.INCOMING,
            conversation_id=CONVERSATION_ID,
            external_message_id="4830",
        ),
        UnhandledGatewayEvent(
            kind="message_created",
            direction=MessageDirection.OUTGOING,
            conversation_id=CONVERSATION_ID,
            external_message_id=EXTERNAL_ID,
        ),
        UnhandledGatewayEvent(
            kind="conversation_status_changed",
            direction=None,
            conversation_id=CONVERSATION_ID,
            external_message_id=None,
        ),
        UnhandledGatewayEvent(
            kind="unknown", direction=None, conversation_id=None, external_message_id=None
        ),
    ],
    ids=["incoming", "outgoing-echo", "conversation", "unknown"],
)
async def test_an_event_that_is_not_a_delivery_notice_is_only_logged(
    event: UnhandledGatewayEvent,
) -> None:
    use_case, store, gateway = _build(event, message=_sent_message())

    with capture_logs() as logs:
        outcome = await use_case.execute(raw_body=RAW_BODY, received_at=RECEIVED_AT)

    assert outcome is GatewayEventOutcome.UNHANDLED
    assert [entry["event"] for entry in logs] == ["gateway_event_unhandled"]
    assert logs[0]["kind"] == event.kind
    assert logs[0]["external_message_id"] == event.external_message_id
    assert gateway.lookups == []
    assert (store.commits, store.rollbacks) == (0, 0)
    assert _stored(store).delivery_status is None


# --- Transacciones ------------------------------------------------------------------------


async def test_an_applied_notice_runs_two_short_transactions_that_commit() -> None:
    use_case, store, _ = _build(_notice(), message=_sent_message())

    await use_case.execute(raw_body=RAW_BODY, received_at=RECEIVED_AT)

    assert (store.commits, store.rollbacks) == (2, 0)


async def test_a_notice_for_an_unknown_message_only_opens_the_check_transaction() -> None:
    use_case, store, _ = _build(_notice())

    await use_case.execute(raw_body=RAW_BODY, received_at=RECEIVED_AT)

    assert (store.commits, store.rollbacks) == (1, 0)


async def test_a_persistence_failure_rolls_back_and_propagates() -> None:
    message = _sent_message()
    use_case, store, _ = _build(_notice(), message=message)
    store.fail_save.add(message.id)

    with pytest.raises(RuntimeError, match="Fallo simulado"):
        await use_case.execute(raw_body=RAW_BODY, received_at=RECEIVED_AT)

    assert (store.commits, store.rollbacks) == (1, 1)
    assert _stored(store).delivery_status is None


# --- Sin datos sensibles en los logs (DSR-7) ----------------------------------------------


async def test_logs_only_carry_identifiers_and_status() -> None:
    cases: list[tuple[GatewayEvent | None, dict[str, object]]] = [
        (_notice(status=DeliveryStatus.FAILED, error="razón"), {"message": _sent_message()}),
        (_notice(), {}),
        (_notice(status=None, status_in_payload=True), {"message": _sent_message()}),
        (_notice(), {"message": _sent_message()}),
        (
            UnhandledGatewayEvent(
                kind="message_created",
                direction=MessageDirection.INCOMING,
                conversation_id=CONVERSATION_ID,
                external_message_id="4830",
            ),
            {},
        ),
    ]
    entries: list[dict[str, object]] = []
    for event, options in cases:
        use_case, _, _ = _build(event, **options)  # type: ignore[arg-type]
        with capture_logs() as logs:
            await use_case.execute(raw_body=RAW_BODY, received_at=RECEIVED_AT, last_attempt=True)
        entries.extend(logs)

    assert entries
    assert all(set(entry) <= ALLOWED_LOG_KEYS for entry in entries)
