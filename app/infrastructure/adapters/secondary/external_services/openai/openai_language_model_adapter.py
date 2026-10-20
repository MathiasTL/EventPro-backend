"""Adaptador de ``ILanguageModelPort`` sobre la Responses API del SDK oficial de OpenAI.

Sin estado en el servidor (``store=False``): el historial completo viaja en cada llamada. Un
mensaje del asistente con herramientas se traduce a un ítem ``function_call`` por herramienta y
su resultado a un ``function_call_output`` con el mismo ``call_id``. Todo fallo del SDK sale
como ``LanguageModelError`` con un código corto; el texto del error nunca se propaga porque
podría citar la conversación.
"""

from collections.abc import Sequence
from typing import Any

import openai
from openai import AsyncOpenAI

from app.application.dtos.language_model_dto import (
    LlmMessage,
    LlmReply,
    LlmRole,
    LlmToolCall,
    LlmToolSpec,
)
from app.application.ports.output.language_model_port import LanguageModelError


class OpenAILanguageModelAdapter:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self._model = model
        # Sin reintentos del SDK: un turno del bot debe caber en el tiempo del trabajo del
        # worker y el motor ya cae al menú ante el primer fallo.
        self._client = client or AsyncOpenAI(
            api_key=api_key, timeout=timeout_seconds, max_retries=0
        )

    async def complete(
        self,
        *,
        system_prompt: str,
        messages: Sequence[LlmMessage],
        tools: Sequence[LlmToolSpec],
    ) -> LlmReply:
        try:
            response = await self._client.responses.create(
                model=self._model,
                instructions=system_prompt,
                input=_to_input_items(messages),  # type: ignore[arg-type]
                tools=[_to_tool(tool) for tool in tools],  # type: ignore[misc]
                store=False,
            )
        except openai.APITimeoutError as error:
            raise LanguageModelError("timeout") from error
        except openai.RateLimitError as error:
            raise LanguageModelError("rate_limit") from error
        except openai.APIConnectionError as error:
            raise LanguageModelError("connection") from error
        except openai.APIError as error:
            raise LanguageModelError("api_error") from error
        calls = tuple(
            LlmToolCall(id=item.call_id, name=item.name, arguments=item.arguments)
            for item in response.output
            if item.type == "function_call"
        )
        text = response.output_text or ""
        if not text and not calls:
            raise LanguageModelError("bad_response")
        return LlmReply(text=text, tool_calls=calls)


def _to_tool(tool: LlmToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "name": tool.name,
        "description": tool.description,
        "parameters": dict(tool.parameters),
        "strict": False,
    }


def _to_input_items(messages: Sequence[LlmMessage]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for message in messages:
        if message.role is LlmRole.USER:
            items.append({"role": "user", "content": message.content})
        elif message.role is LlmRole.ASSISTANT:
            if message.content:
                items.append({"role": "assistant", "content": message.content})
            items.extend(
                {
                    "type": "function_call",
                    "call_id": call.id,
                    "name": call.name,
                    "arguments": call.arguments,
                }
                for call in message.tool_calls
            )
        else:
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": message.tool_call_id,
                    "output": message.content,
                }
            )
    return items
