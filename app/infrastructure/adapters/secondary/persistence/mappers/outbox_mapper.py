"""Conversión explícita entre OutboxMessageModel y el agregado OutboxMessage."""

import copy

from app.domain.entities.outbox_message import OutboxMessage
from app.domain.value_objects.outbox import DeliveryStatus, MessageType, OutboxStatus
from app.domain.value_objects.phone_number import PhoneNumber
from app.infrastructure.adapters.secondary.persistence.models.outbox_message_model import (
    OutboxMessageModel,
)


def outbox_to_domain(row: OutboxMessageModel) -> OutboxMessage:
    """Reconstruye el agregado sin revalidar el contenido: un payload anulado es legítimo."""

    return OutboxMessage(
        id=row.id,
        recipient=PhoneNumber.parse(row.recipient_phone),
        message_type=MessageType(row.message_type),
        payload=copy.deepcopy(row.payload) if row.payload is not None else None,
        redact_after_send=row.redact_after_send,
        status=OutboxStatus(row.status),
        attempts=row.attempts,
        max_attempts=row.max_attempts,
        next_attempt_at=row.next_attempt_at,
        last_error=row.last_error,
        sent_at=row.sent_at,
        created_at=row.created_at,
        external_message_id=row.external_message_id,
        conversation_id=row.conversation_id,
        delivery_status=DeliveryStatus(row.delivery_status) if row.delivery_status else None,
        delivery_error=row.delivery_error,
        delivered_at=row.delivered_at,
        read_at=row.read_at,
        author_user_id=row.author_user_id,
        retried_external_message_id=row.retried_external_message_id,
    )


def apply_outbox_to_model(row: OutboxMessageModel, message: OutboxMessage) -> None:
    """Copia el estado mutable del agregado; destinatario, tipo, autor e id no cambian."""

    row.payload = copy.deepcopy(message.payload) if message.payload is not None else None
    row.redact_after_send = message.redact_after_send
    row.status = message.status.value
    row.attempts = message.attempts
    row.max_attempts = message.max_attempts
    row.next_attempt_at = message.next_attempt_at
    row.last_error = message.last_error
    row.sent_at = message.sent_at
    row.external_message_id = message.external_message_id
    row.conversation_id = message.conversation_id
    row.delivery_status = message.delivery_status.value if message.delivery_status else None
    row.delivery_error = message.delivery_error
    row.delivered_at = message.delivered_at
    row.read_at = message.read_at
    row.retried_external_message_id = message.retried_external_message_id


def outbox_to_model(message: OutboxMessage) -> OutboxMessageModel:
    row = OutboxMessageModel(
        id=message.id,
        recipient_phone=message.recipient.value,
        message_type=message.message_type.value,
        created_at=message.created_at,
        author_user_id=message.author_user_id,
    )
    apply_outbox_to_model(row, message)
    return row
