"""OpenAILanguageModelAdapter: traducción a la Responses API y errores del SDK, sin red."""

from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest

from app.application.dtos.language_model_dto import (
    LlmMessage,
    LlmRole,
    LlmToolCall,
    LlmToolSpec,
)
from app.application.ports.output.language_model_port import LanguageModelError
from app.infrastructure.adapters.secondary.external_services.openai.openai_language_model_adapter import (  # noqa: E501
    OpenAILanguageModelAdapter,
)

_REQUEST = httpx.Request("POST", "https://api.openai.com/v1/responses")
_TOOL = LlmToolSpec("list_catalog", "Lists the catalog", {"type": "object", "properties": {}})


class _Responses:
    def __init__(self, outcome: Any) -> None:
        self.outcome = outcome
        self.kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def _adapter(outcome: Any) -> tuple[OpenAILanguageModelAdapter, _Responses]:
    responses = _Responses(outcome)
    client: Any = SimpleNamespace(responses=responses)
    adapter = OpenAILanguageModelAdapter(
        api_key="test-key", model="gpt-test", timeout_seconds=5, client=client
    )
    return adapter, responses


def _response(*items: Any, text: str = "") -> Any:
    return SimpleNamespace(output=list(items), output_text=text)


async def test_the_history_and_tools_are_sent_as_responses_api_items() -> None:
    adapter, responses = _adapter(_response(text="Hola"))
    history = [
        LlmMessage(LlmRole.USER, "quiero cotizar"),
        LlmMessage(LlmRole.ASSISTANT, "Un momento", (LlmToolCall("c1", "list_catalog", "{}"),)),
        LlmMessage(LlmRole.TOOL, '{"ok": true}', tool_call_id="c1"),
        LlmMessage(LlmRole.ASSISTANT, "Tenemos estos paquetes"),
    ]

    reply = await adapter.complete(system_prompt="sé breve", messages=history, tools=[_TOOL])

    assert reply.text == "Hola"
    assert reply.tool_calls == ()
    sent = responses.kwargs
    assert sent["model"] == "gpt-test"
    assert sent["instructions"] == "sé breve"
    assert sent["store"] is False
    assert sent["input"] == [
        {"role": "user", "content": "quiero cotizar"},
        {"role": "assistant", "content": "Un momento"},
        {"type": "function_call", "call_id": "c1", "name": "list_catalog", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "c1", "output": '{"ok": true}'},
        {"role": "assistant", "content": "Tenemos estos paquetes"},
    ]
    assert sent["tools"] == [
        {
            "type": "function",
            "name": "list_catalog",
            "description": "Lists the catalog",
            "parameters": {"type": "object", "properties": {}},
            "strict": False,
        }
    ]


async def test_function_calls_in_the_output_become_tool_calls() -> None:
    call = SimpleNamespace(type="function_call", call_id="c9", name="pay_advance", arguments="{}")
    message = SimpleNamespace(type="message")
    adapter, _ = _adapter(_response(message, call))

    reply = await adapter.complete(system_prompt="", messages=[], tools=[_TOOL])

    assert reply.tool_calls == (LlmToolCall("c9", "pay_advance", "{}"),)


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (openai.APITimeoutError(request=_REQUEST), "timeout"),
        (openai.APIConnectionError(request=_REQUEST), "connection"),
        (
            openai.RateLimitError(
                "limit", response=httpx.Response(429, request=_REQUEST), body=None
            ),
            "rate_limit",
        ),
        (
            openai.AuthenticationError(
                "bad key", response=httpx.Response(401, request=_REQUEST), body=None
            ),
            "api_error",
        ),
    ],
)
async def test_sdk_errors_become_one_language_model_error_without_their_text(
    error: Exception, reason: str
) -> None:
    adapter, _ = _adapter(error)

    with pytest.raises(LanguageModelError) as raised:
        await adapter.complete(system_prompt="", messages=[], tools=[])

    assert raised.value.reason == reason
    assert "bad key" not in str(raised.value)


async def test_an_empty_response_is_a_bad_response() -> None:
    adapter, _ = _adapter(_response())

    with pytest.raises(LanguageModelError) as raised:
        await adapter.complete(system_prompt="", messages=[], tools=[])

    assert raised.value.reason == "bad_response"
