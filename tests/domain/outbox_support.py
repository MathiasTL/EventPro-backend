"""Fábrica de OutboxMessage compartida por las pruebas de dominio y de casos de uso."""

from datetime import UTC, datetime
from typing import Any

from app.domain.entities.outbox_message import OutboxMessage
from app.domain.value_objects.outbox import MessageType
from app.domain.value_objects.phone_number import PhoneNumber

NOW = datetime(2026, 10, 9, 15, 0, tzinfo=UTC)
PHONE = PhoneNumber.parse("999111222")

TEXT_PAYLOAD: dict[str, Any] = {"body": "Hola, tu cotización está lista"}
TEMPLATE_PAYLOAD: dict[str, Any] = {"name": "cotizacion_lista", "params": {"nombre": "Ana"}}
INTERACTIVE_PAYLOAD: dict[str, Any] = {
    "body": "Elige un paquete",
    "sections": [
        {
            "title": "Paquetes",
            "rows": [{"id": "pkg-1", "title": "Show infantil", "description": "2 h"}],
        }
    ],
}
DOCUMENT_PAYLOAD: dict[str, Any] = {
    "path": "database/contracts/abc",
    "filename": "contrato.pdf",
    "content_type": "application/pdf",
    "caption": "Tu contrato",
}


def make_message(
    *,
    message_type: MessageType = MessageType.TEXT,
    payload: dict[str, Any] | None = None,
    now: datetime = NOW,
    **overrides: Any,
) -> OutboxMessage:
    default_payloads = {
        MessageType.TEXT: TEXT_PAYLOAD,
        MessageType.TEMPLATE: TEMPLATE_PAYLOAD,
        MessageType.INTERACTIVE: INTERACTIVE_PAYLOAD,
        MessageType.DOCUMENT: DOCUMENT_PAYLOAD,
    }
    return OutboxMessage.create(
        recipient=overrides.pop("recipient", PHONE),
        message_type=message_type,
        payload=payload if payload is not None else default_payloads[message_type],
        now=now,
        **overrides,
    )
