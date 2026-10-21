"""Estado de la conversación cuando responde el agente: historial, cotización y pago.

Se guarda en el mismo puerto de sesiones que el motor de menús, con la marca ``engine`` para
distinguirlos: una sesión de menús (que tiene ``step``) nunca se interpreta como del agente ni
al revés. El historial se recorta a una ventana segura para no crecer sin límite.
"""

from dataclasses import dataclass, field
from typing import Any

from app.application.dtos.language_model_dto import LlmMessage, LlmRole

ENGINE_KEY = "engine"
AGENT_ENGINE = "agent"
# Mensajes que se conservan; el recorte nunca separa una herramienta de su resultado.
MAX_HISTORY_MESSAGES = 40


def trim_history(
    history: list[LlmMessage], max_messages: int = MAX_HISTORY_MESSAGES
) -> list[LlmMessage]:
    """Últimos ``max_messages`` mensajes, empezando siempre en un mensaje del cliente.

    Un ``TOOL`` sin el ``ASSISTANT`` que lo pidió (o al revés) haría que el proveedor rechace
    la petición, así que se descarta desde el principio hasta llegar a un mensaje ``USER``.
    """

    if len(history) <= max_messages:
        return list(history)
    trimmed = history[-max_messages:]
    while trimmed and trimmed[0].role is not LlmRole.USER:
        trimmed = trimmed[1:]
    return trimmed


@dataclass
class AgentSession:
    history: list[LlmMessage] = field(default_factory=list)
    quote_id: str | None = None
    # Paquete, temática, fecha y distrito de la cotización: datos para el resumen de derivación.
    quote_details: str | None = None
    payment_started: bool = False
    # Último mensaje ya procesado: un reintento del trabajo no responde dos veces.
    last_message_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            ENGINE_KEY: AGENT_ENGINE,
            "history": [message.to_dict() for message in self.history],
            "quote_id": self.quote_id,
            "quote_details": self.quote_details,
            "payment_started": self.payment_started,
            "last_message_id": self.last_message_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentSession | None":
        """Reconstruye la sesión; ``None`` si no es del agente o su forma no es la esperada."""

        if data.get(ENGINE_KEY) != AGENT_ENGINE:
            return None
        try:
            return cls(
                history=[LlmMessage.from_dict(item) for item in data.get("history", [])],
                quote_id=data.get("quote_id"),
                quote_details=data.get("quote_details"),
                payment_started=bool(data.get("payment_started", False)),
                last_message_id=data.get("last_message_id"),
            )
        except (KeyError, TypeError, ValueError):
            return None
