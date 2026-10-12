"""Agregado OutboxMessage: envío con reintentos y seguimiento de entrega (E1, RNF-03.2).

Forma del ``payload`` según ``message_type``:

* ``TEXT``: ``{"body": str}``.
* ``TEMPLATE``: ``{"name": str, "params": {str: str}}``.
* ``INTERACTIVE``: ``{"body": str, "sections": [{"title": str, "rows": [{"id": str,
  "title": str, "description": str | None}]}]}``.
* ``DOCUMENT``: ``{"path": str, "filename": str, "content_type": str, "caption": str | None}``;
  los bytes no se guardan, solo la ruta del archivo en el almacenamiento.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Self
from uuid import UUID, uuid4

from app.domain.exceptions.outbox_exceptions import InvalidOutboxStateError
from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.outbox import (
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_RETRY_SCHEDULE,
    DeliveryStatus,
    MessageType,
    OutboxStatus,
    RetrySchedule,
)
from app.domain.value_objects.phone_number import PhoneNumber

_ERROR_MAX_LENGTH = 500
_EXTERNAL_ID_MAX_LENGTH = 64
_UNKNOWN_ERROR = "Error desconocido"


def _require_aware(value: datetime, name: str) -> datetime:
    """Exige un instante con zona horaria y lo normaliza a UTC."""

    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError(f"{name} debe incluir zona horaria")
    return value.astimezone(UTC)


def _clip(error: str | None) -> str | None:
    if error is None:
        return None
    return error.strip()[:_ERROR_MAX_LENGTH] or _UNKNOWN_ERROR


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label} debe ser un texto no vacío")
    return value


def _optional_text(value: object, label: str) -> str | None:
    return None if value is None else _text(value, label)


def _validate_params(value: object) -> None:
    if not isinstance(value, dict):
        raise ValidationError("params debe ser un objeto de texto a texto")
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise ValidationError("params debe ser un objeto de texto a texto")


def _validate_sections(value: object) -> None:
    if not isinstance(value, list) or not value:
        raise ValidationError("sections debe ser una lista no vacía")
    for section in value:
        if not isinstance(section, dict):
            raise ValidationError("Cada sección debe ser un objeto")
        _text(section.get("title"), "El título de la sección")
        rows = section.get("rows")
        if not isinstance(rows, list) or not rows:
            raise ValidationError("Cada sección debe incluir filas")
        for row in rows:
            if not isinstance(row, dict):
                raise ValidationError("Cada fila debe ser un objeto")
            _text(row.get("id"), "El id de la fila")
            _text(row.get("title"), "El título de la fila")
            _optional_text(row.get("description"), "La descripción de la fila")


def validate_payload(message_type: MessageType, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Valida que ``payload`` sea coherente con ``message_type`` y devuelve una copia."""

    if not isinstance(payload, Mapping):
        raise ValidationError("El contenido del mensaje debe ser un objeto")
    if message_type is MessageType.TEXT:
        _text(payload.get("body"), "body")
    elif message_type is MessageType.TEMPLATE:
        _text(payload.get("name"), "name")
        _validate_params(payload.get("params"))
    elif message_type is MessageType.INTERACTIVE:
        _text(payload.get("body"), "body")
        _validate_sections(payload.get("sections"))
    else:
        _text(payload.get("path"), "path")
        _text(payload.get("filename"), "filename")
        _text(payload.get("content_type"), "content_type")
        _optional_text(payload.get("caption"), "caption")
    return copy.deepcopy(dict(payload))


@dataclass(kw_only=True)
class OutboxMessage:
    recipient: PhoneNumber
    message_type: MessageType
    payload: dict[str, Any] | None
    next_attempt_at: datetime
    created_at: datetime
    redact_after_send: bool = False
    status: OutboxStatus = OutboxStatus.PENDING
    attempts: int = 0
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    last_error: str | None = None
    sent_at: datetime | None = None
    external_message_id: str | None = None
    conversation_id: int | None = None
    delivery_status: DeliveryStatus | None = None
    delivery_error: str | None = None
    delivered_at: datetime | None = None
    read_at: datetime | None = None
    id: UUID = field(default_factory=uuid4)

    @classmethod
    def create(
        cls,
        *,
        recipient: PhoneNumber,
        message_type: MessageType,
        payload: Mapping[str, Any],
        now: datetime,
        redact_after_send: bool = False,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> Self:
        """Nace ``PENDING`` con ``attempts = 0`` y listo para despacharse en ``now``."""

        moment = _require_aware(now, "now")
        if not isinstance(recipient, PhoneNumber):
            raise ValidationError("recipient debe ser un PhoneNumber")
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or max_attempts < 1:
            raise ValidationError("max_attempts debe ser un entero mayor que cero")
        return cls(
            recipient=recipient,
            message_type=message_type,
            payload=validate_payload(message_type, payload),
            redact_after_send=redact_after_send,
            max_attempts=max_attempts,
            next_attempt_at=moment,
            created_at=moment,
        )

    def mark_sent(self, *, external_message_id: str, conversation_id: int, now: datetime) -> None:
        """Chatwoot aceptó el mensaje; anula el contenido si ``redact_after_send``."""

        self._require_pending("marcar como enviado")
        moment = _require_aware(now, "now")
        if (
            not isinstance(external_message_id, str)
            or not external_message_id.strip()
            or len(external_message_id) > _EXTERNAL_ID_MAX_LENGTH
        ):
            raise ValidationError("external_message_id debe tener entre 1 y 64 caracteres")
        self.status = OutboxStatus.SENT
        self.sent_at = moment
        self.external_message_id = external_message_id
        self.conversation_id = conversation_id
        if self.redact_after_send:
            self.payload = None

    def register_failure(
        self,
        *,
        error: str,
        permanent: bool,
        now: datetime,
        schedule: RetrySchedule = DEFAULT_RETRY_SCHEDULE,
    ) -> OutboxStatus:
        """Suma un intento; pasa a ``FAILED`` si es permanente o se agotaron los intentos.

        Devuelve el estado resultante: ``PENDING`` si se reprogramó, ``FAILED`` si no.
        """

        self._require_pending("registrar un fallo")
        moment = _require_aware(now, "now")
        self.attempts += 1
        self.last_error = _clip(error) or _UNKNOWN_ERROR
        if permanent or self.attempts >= self.max_attempts:
            self.status = OutboxStatus.FAILED
            return self.status
        self.next_attempt_at = moment + schedule.delay_after(self.attempts)
        return self.status

    def record_delivery(self, *, status: DeliveryStatus, error: str | None, at: datetime) -> bool:
        """Aplica el aviso de entrega de WhatsApp sin retroceder; ``False`` si se ignoró."""

        if self.status is not OutboxStatus.SENT:
            raise InvalidOutboxStateError(
                f"No se puede registrar la entrega de un mensaje en estado {self.status}"
            )
        moment = _require_aware(at, "at")
        current = self.delivery_status
        settled = (DeliveryStatus.DELIVERED, DeliveryStatus.READ)
        if status is DeliveryStatus.FAILED:
            if current in settled:
                return False
            self.delivery_status = DeliveryStatus.FAILED
            self.delivery_error = _clip(error)
            return True
        if status is DeliveryStatus.DELIVERED:
            if current in settled:
                return False
            self.delivery_status = DeliveryStatus.DELIVERED
            self.delivery_error = None
            self.delivered_at = moment
            return True
        if current is DeliveryStatus.READ:
            return False
        self.delivery_status = DeliveryStatus.READ
        self.delivery_error = None
        self.delivered_at = self.delivered_at or moment
        self.read_at = moment
        return True

    def retry(self, *, now: datetime) -> None:
        """Reencola un mensaje ``FAILED`` (por envío o por rechazo de WhatsApp)."""

        if (
            self.status is not OutboxStatus.FAILED
            and self.delivery_status is not DeliveryStatus.FAILED
        ):
            raise InvalidOutboxStateError(
                "Solo se puede reintentar un mensaje con envío o entrega fallidos"
            )
        moment = _require_aware(now, "now")
        if self.payload is None:
            raise InvalidOutboxStateError(
                "El contenido se anuló tras el envío; el mensaje no puede reintentarse"
            )
        self.status = OutboxStatus.PENDING
        self.attempts = 0
        self.next_attempt_at = moment
        self.last_error = None
        self.sent_at = None
        self.external_message_id = None
        self.conversation_id = None
        self.delivery_status = None
        self.delivery_error = None
        self.delivered_at = None
        self.read_at = None

    def _require_pending(self, action: str) -> None:
        if self.status is not OutboxStatus.PENDING:
            raise InvalidOutboxStateError(
                f"No se puede {action} un mensaje en estado {self.status}"
            )
