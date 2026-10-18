"""Objetos de valor de la cola de mensajes salientes (outbox) de E1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum

from app.domain.exceptions.resource_exceptions import ValidationError

# RNF-03.2: cinco reintentos más el primer envío suman seis intentos.
DEFAULT_MAX_ATTEMPTS = 6


class OutboxStatus(StrEnum):
    """Responde: ¿se entregó el mensaje a Chatwoot? ``SENT`` significa que Chatwoot lo aceptó."""

    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"


class DeliveryStatus(StrEnum):
    """Responde: ¿WhatsApp lo entregó al cliente? Lo informa el webhook de Chatwoot."""

    DELIVERED = "DELIVERED"
    READ = "READ"
    FAILED = "FAILED"


class MessageType(StrEnum):
    TEXT = "TEXT"
    TEMPLATE = "TEMPLATE"
    INTERACTIVE = "INTERACTIVE"
    DOCUMENT = "DOCUMENT"


@dataclass(frozen=True)
class RetrySchedule:
    """Espera creciente entre intentos: ``delays[n - 1]`` tras el intento fallido ``n``."""

    delays: tuple[timedelta, ...]

    def __post_init__(self) -> None:
        if not self.delays or any(delay <= timedelta(0) for delay in self.delays):
            raise ValidationError("La espera entre intentos debe ser positiva y no estar vacía")

    def delay_after(self, failed_attempts: int) -> timedelta:
        """Espera tras el intento fallido ``failed_attempts``; se repite la última si se excede."""

        if (
            isinstance(failed_attempts, bool)
            or not isinstance(failed_attempts, int)
            or failed_attempts < 1
        ):
            raise ValidationError("failed_attempts debe ser un entero mayor o igual que 1")
        return self.delays[min(failed_attempts, len(self.delays)) - 1]


DEFAULT_RETRY_SCHEDULE = RetrySchedule(
    (
        timedelta(seconds=30),
        timedelta(minutes=2),
        timedelta(minutes=10),
        timedelta(minutes=30),
        timedelta(hours=2),
    )
)
