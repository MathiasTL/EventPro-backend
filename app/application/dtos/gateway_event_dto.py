"""DTOs de los eventos que el gateway de mensajería informa a la aplicación."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.application.dtos.messaging_dto import (
    ConversationLifecycle,
    ConversationStatus,
    MessageAttachment,
    MessageDirection,
    MessageSender,
)
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
class ConversationSnapshot:
    """Estado de la conversación que Chatwoot incrusta en el evento de un mensaje (6.1).

    ``contact_name`` es el nombre del contacto de Chatwoot, no el del cliente de EventPro.
    """

    lifecycle: ConversationLifecycle
    unread_count: int = 0
    can_reply: bool = False
    contact_phone: PhoneNumber | None = None
    contact_name: str | None = None


@dataclass(frozen=True)
class MessageDetails:
    """Datos del mensaje que el bot no necesita pero la bandeja sí.

    ``sent_at`` es ``None`` si el evento no trae hora legible. ``delivery_status`` y ``error``
    son los que el mensaje ya trae al crearse (Chatwoot puede rechazarlo de inmediato).
    """

    sent_at: datetime | None = None
    sender: MessageSender | None = None
    sender_name: str | None = None
    attachments: Sequence[MessageAttachment] = ()
    delivery_status: DeliveryStatus | None = None
    error: str | None = None


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
    snapshot: ConversationSnapshot | None = None
    details: MessageDetails = MessageDetails()


@dataclass(frozen=True)
class OutgoingMessageEcho:
    """Eco de ``message_created`` de un mensaje saliente (del bot o de un encargado).

    No lleva teléfono: el bot nunca lo atiende; la bandeja lo publica con su autoría.
    """

    external_message_id: str
    conversation_id: int
    content: str
    snapshot: ConversationSnapshot | None = None
    details: MessageDetails = MessageDetails()


GatewayEvent = DeliveryNotice | IncomingClientMessage | OutgoingMessageEcho | UnhandledGatewayEvent


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
