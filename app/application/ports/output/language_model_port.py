from collections.abc import Sequence
from typing import Protocol

from app.application.dtos.language_model_dto import LlmMessage, LlmReply, LlmToolSpec


class LanguageModelError(Exception):
    """El modelo de lenguaje no respondió: tiempo agotado, límite, red o respuesta inválida.

    ``reason`` es un código corto (``timeout``, ``rate_limit``, ``connection``, ``api_error``,
    ``bad_response``, ``budget``) sin contenido de la conversación, apto para el log.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ILanguageModelPort(Protocol):
    """Un turno de un modelo de lenguaje con herramientas, sin depender del proveedor."""

    async def complete(
        self,
        *,
        system_prompt: str,
        messages: Sequence[LlmMessage],
        tools: Sequence[LlmToolSpec],
    ) -> LlmReply:
        """Siguiente respuesta del asistente dado el historial.

        Lanza ``LanguageModelError`` ante cualquier fallo del proveedor.
        """
