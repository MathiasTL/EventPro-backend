"""DTOs del modelo de lenguaje, agnósticos del proveedor (E1, agente conversacional).

El historial de una conversación se guarda en la sesión del bot como JSON, por eso los
mensajes saben convertirse a ``dict`` y reconstruirse. Los argumentos de una herramienta viajan
como el texto JSON que emitió el modelo: validarlos es tarea del motor del agente.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class LlmRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(frozen=True)
class LlmToolCall:
    """Herramienta que el modelo pide ejecutar; ``arguments`` es texto JSON."""

    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class LlmMessage:
    """Un mensaje del historial.

    ``USER``: ``content`` es lo que escribió el cliente. ``ASSISTANT``: ``content`` es el texto
    (puede ser vacío) y ``tool_calls`` lo que pidió ejecutar. ``TOOL``: ``content`` es el
    resultado en JSON de la herramienta ``tool_call_id``.
    """

    role: LlmRole
    content: str = ""
    tool_calls: tuple[LlmToolCall, ...] = ()
    tool_call_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role.value,
            "content": self.content,
            "tool_calls": [
                {"id": call.id, "name": call.name, "arguments": call.arguments}
                for call in self.tool_calls
            ],
            "tool_call_id": self.tool_call_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "LlmMessage":
        """Reconstruye el mensaje; lanza ``KeyError``/``ValueError`` si la forma es inválida."""

        return cls(
            role=LlmRole(data["role"]),
            content=str(data.get("content") or ""),
            tool_calls=tuple(
                LlmToolCall(str(call["id"]), str(call["name"]), str(call["arguments"]))
                for call in data.get("tool_calls") or []
            ),
            tool_call_id=data.get("tool_call_id"),
        )


@dataclass(frozen=True)
class LlmToolSpec:
    """Herramienta que se ofrece al modelo; ``parameters`` es un JSON Schema de objeto."""

    name: str
    description: str
    parameters: Mapping[str, Any]


@dataclass(frozen=True)
class LlmReply:
    """Respuesta del modelo: texto, herramientas pedidas, o ambos."""

    text: str = ""
    tool_calls: tuple[LlmToolCall, ...] = ()
