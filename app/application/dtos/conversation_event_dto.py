"""Sobre de los eventos de la bandeja que viajan del worker y la API al navegador (D4).

``data`` solo lleva valores JSON (texto, números, booleanos, ``None``, listas y objetos): el
publicador lo serializa tal cual. Los eventos pueden llevar texto de mensajes; viajan por
*pub/sub* sin persistirse (5.3).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

EVENT_ENVELOPE_VERSION = 1


class ConversationEventType(StrEnum):
    CONVERSATION_UPDATED = "conversation.updated"
    MESSAGE_CREATED = "message.created"
    MESSAGE_UPDATED = "message.updated"
    HANDOFF_REQUESTED = "handoff.requested"


@dataclass(frozen=True)
class ConversationEvent:
    event: ConversationEventType
    data: Mapping[str, Any]
    v: int = EVENT_ENVELOPE_VERSION

    def to_envelope(self) -> dict[str, Any]:
        """``{"v": 1, "event": "<nombre>", "data": {...}}``, listo para serializar."""

        return {"v": self.v, "event": self.event.value, "data": dict(self.data)}
