"""DTOs de los eventos que el gateway de mensajería informa a la aplicación."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.application.dtos.messaging_dto import ConversationStatus, MessageDirection
from app.domain.value_objects.outbox import DeliveryStatus
from app.domain.value_objects.phone_number import PhoneNumber


@dataclass(frozen=True)
class DeliveryNotice:
    """Aviso de que el estado de un mensaje saliente cambió.

    ``status`` es ``None`` cuando el aviso no trae un estado que se pueda registrar;
    ``status_in_payload`` distingue "el aviso no lo dice" (hay que consultarlo) de "lo dice
    pero no se registra" (por ejemplo ``sent``). ``updated_at`` es la hora de actualización
    que informa el aviso, si la trae.
    """

    external_message_id: str
    conversation_id: int | None
    status: DeliveryStatus | None
    error: str | None
    updated_at: datetime | None = None
    status_in_payload: bool = False


@dataclass(frozen=True)
class UnhandledGatewayEvent:
    """Evento válido que esta etapa solo registra en el log (sin contenido ni teléfonos)."""

    kind: str
    direction: MessageDirection | None
    conversation_id: int | None
    external_message_id: str | None


@dataclass(frozen=True)
class IncomingClientMessage:
    """Mensaje de texto que un cliente escribió; el bot decide si lo responde.

    ``content`` es vacío cuando el mensaje solo trae adjuntos. ``is_private`` marca las notas
    internas de un encargado, que nunca deben recibir respuesta.
    """

    external_message_id: str
    conversation_id: int
    conversation_status: ConversationStatus
    sender_phone: PhoneNumber
    content: str
    is_private: bool = False


GatewayEvent = DeliveryNotice | IncomingClientMessage | UnhandledGatewayEvent


@dataclass(frozen=True)
class DeliveryReport:
    """Estado de un mensaje según la API del gateway; ``status`` ``None``: aún sin entregar."""

    status: DeliveryStatus | None
    error: str | None


class GatewayEventOutcome(StrEnum):
    APPLIED = "APPLIED"
    IGNORED = "IGNORED"
    UNKNOWN_MESSAGE = "UNKNOWN_MESSAGE"
    UNRESOLVED = "UNRESOLVED"
    UNHANDLED = "UNHANDLED"
    MALFORMED = "MALFORMED"
