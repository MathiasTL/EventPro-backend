"""Modelo de lenguaje con guion para probar el agente del bot sin red."""

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from app.application.dtos.language_model_dto import LlmMessage, LlmReply, LlmToolCall, LlmToolSpec
from app.application.ports.output.language_model_port import LanguageModelError

Step = LlmReply | LanguageModelError


@dataclass
class ModelCall:
    system_prompt: str
    messages: list[LlmMessage]
    tools: list[LlmToolSpec]


@dataclass
class ScriptedLanguageModel:
    """Responde con los pasos del guion, en orden; un paso de error se lanza."""

    steps: list[Step]
    calls: list[ModelCall] = field(default_factory=list)

    async def complete(
        self,
        *,
        system_prompt: str,
        messages: Sequence[LlmMessage],
        tools: Sequence[LlmToolSpec],
    ) -> LlmReply:
        self.calls.append(ModelCall(system_prompt, list(messages), list(tools)))
        if not self.steps:
            raise AssertionError("El guion del modelo se agotó")
        step = self.steps.pop(0)
        if isinstance(step, LanguageModelError):
            raise step
        return step


def say(text: str) -> LlmReply:
    return LlmReply(text=text)


def call(name: str, call_id: str = "call_1", **arguments: Any) -> LlmReply:
    return LlmReply(tool_calls=(LlmToolCall(call_id, name, json.dumps(arguments)),))


def raw_call(name: str, arguments: str, call_id: str = "call_1") -> LlmReply:
    return LlmReply(tool_calls=(LlmToolCall(call_id, name, arguments),))
