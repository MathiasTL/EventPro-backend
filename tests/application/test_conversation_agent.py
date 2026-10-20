"""Agente conversacional del bot: herramientas, errores de negocio, límites y respaldo."""

import asyncio
import json
import re
from typing import Any

import pytest
from structlog.testing import capture_logs

from app.application.dtos.gateway_event_dto import GatewayEventOutcome
from app.application.dtos.language_model_dto import LlmMessage, LlmReply, LlmRole
from app.application.dtos.messaging_dto import ConversationStatus
from app.application.ports.output.language_model_port import LanguageModelError
from app.application.use_cases.bot import agent_prompt
from app.application.use_cases.bot import bot_messages as texts
from app.application.use_cases.bot.agent_engine import (
    ATTACHMENT_PLACEHOLDER,
    MAX_TOOL_ITERATIONS,
)
from app.application.use_cases.bot.agent_session import (
    MAX_HISTORY_MESSAGES,
    AgentSession,
    trim_history,
)
from app.application.use_cases.bot.bot_session import BotSession, BotStep
from app.infrastructure.adapters.secondary.external_services.fake_quote_use_cases import (
    FakeScenario,
)
from tests.application.agent_support import ScriptedLanguageModel, call, raw_call, say
from tests.application.bot_support import (
    BASIC,
    CONVERSATION_ID,
    PHOTOS,
    PREMIUM,
    SAFARI,
    SELVA,
    BotHarness,
)

VOSEO = re.compile(
    r"\b(vos|tenés|tenes|podés|podes|elegí|elegi|escribí|escribi|hacé|mandá|decime|querés|sabés)\b",
    re.IGNORECASE,
)

QUOTE_ARGS: dict[str, Any] = {
    "package_id": str(PREMIUM.id),
    "theme_id": str(SELVA.id),
    "extras": [{"extra_id": str(PHOTOS.id), "quantity": 1}],
    "event_date": "2026-11-15",
    "event_time": "16:30",
    "district": "Lima",
    "address": "Av. Larco 123, frente al parque",
    "full_name": "Ana Torres Quispe",
    "client_provides_mobility": False,
    "observations": None,
}


def _agent_bot(*steps: Any, **options: Any) -> tuple[BotHarness, ScriptedLanguageModel]:
    model = ScriptedLanguageModel(list(steps))
    return BotHarness(model=model, **options), model


async def _agent_session(bot: BotHarness) -> AgentSession:
    stored = await bot.sessions.get(CONVERSATION_ID)
    assert stored is not None
    session = AgentSession.from_dict(stored)
    assert session is not None
    return session


def _tool_results(model: ScriptedLanguageModel) -> list[dict[str, Any]]:
    """Resultados de herramientas que el modelo vio en su última llamada."""

    return [
        json.loads(message.content)
        for message in model.calls[-1].messages
        if message.role is LlmRole.TOOL
    ]


# --- Camino feliz ----------------------------------------------------------------------------


async def test_a_client_quotes_and_pays_the_advance_through_tool_calls() -> None:
    bot, model = _agent_bot(
        call("list_catalog"),
        say("Tenemos Decoración Premium. ¿Qué temática te gusta?"),
        call("create_quote", **QUOTE_ARGS),
        say("Listo, ¿quieres pagar el adelanto para reservar?"),
        call("pay_advance"),
        say("Envía aquí la captura de tu pago y un encargado la validará."),
    )

    first = await bot.say("hola, quiero decoración")
    assert first == "Tenemos Decoración Premium. ¿Qué temática te gusta?"
    catalog = _tool_results(model)[0]
    assert catalog["ok"] is True
    assert {package["name"] for package in catalog["packages"]} >= {"Decoración Premium"}
    premium = next(p for p in catalog["packages"] if p["id"] == str(PREMIUM.id))
    assert premium["base_price"] == "S/ 900.00"
    assert [theme["name"] for theme in premium["compatible_themes"]] == ["Selva", "Safari"]

    created = await bot.say("sí, confirmo todo")
    summary, follow_up = created.split("\n", 1)[0], created.rsplit("\n", 1)[-1]
    assert summary == "Este es el resumen de tu cotización:"
    assert "Paquete: Decoración Premium" in created
    assert "Temática: Selva" in created
    assert "Extras: Fotografía" in created
    assert "Total: S/ 1,080.50" in created
    assert follow_up == "Listo, ¿quieres pagar el adelanto para reservar?"
    session = await _agent_session(bot)
    assert session.quote_id is not None

    paid = await bot.say("pagar adelanto")
    assert "Yape: +51900111222" in paid
    assert paid.endswith("un encargado la validará.")
    assert (await _agent_session(bot)).payment_started is True
    assert bot.messaging.statuses == []
    assert bot.last_outcome is GatewayEventOutcome.APPLIED


async def test_the_model_sees_the_prompt_the_tools_and_the_whole_history() -> None:
    bot, model = _agent_bot(say("Hola, soy el asistente."), say("Claro."))

    await bot.say("hola")
    await bot.say("gracias")

    first, second = model.calls
    assert "Hoy es 09/10/2026 (2026-10-09)" in first.system_prompt
    assert [tool.name for tool in first.tools] == [
        "list_catalog",
        "create_quote",
        "pay_advance",
        "request_handoff",
    ]
    assert [(m.role, m.content) for m in second.messages] == [
        (LlmRole.USER, "hola"),
        (LlmRole.ASSISTANT, "Hola, soy el asistente."),
        (LlmRole.USER, "gracias"),
    ]


def test_the_system_prompt_is_neutral_spanish_without_voseo() -> None:
    from datetime import date

    prompt = agent_prompt.build_system_prompt(date(2026, 10, 9))

    assert VOSEO.search(prompt) is None
    assert "nunca inventes" in prompt.lower()
    assert "Lima y Callao" in prompt


# --- Errores de contrato devueltos al modelo -------------------------------------------------


async def test_an_availability_rejection_reaches_the_model_with_its_alternatives() -> None:
    bot, model = _agent_bot(
        call("create_quote", **QUOTE_ARGS),
        say("Esa fecha no está libre. ¿Te sirve el 15/10 a las 18:00?"),
    )
    bot.create_quote.scenario = FakeScenario.AVAILABILITY_CONFLICT

    reply = await bot.say("confirmo")

    assert reply == "Esa fecha no está libre. ¿Te sirve el 15/10 a las 18:00?"
    (result,) = _tool_results(model)
    assert result["ok"] is False
    assert result["error"] == "availability_rejected"
    assert result["alternatives"] == [{"date": "2026-10-15", "time": "18:00"}]
    assert result["handoff_available"] is True
    assert (await _agent_session(bot)).quote_id is None
    assert "resumen de tu cotización" not in "".join(
        bot.sent
    )  # el turno de la herramienta se revirtió


async def test_a_port_validation_error_is_a_tool_result_not_a_handoff() -> None:
    bot, model = _agent_bot(call("create_quote", **QUOTE_ARGS), say("Revisemos la fecha."))
    bot.create_quote.scenario = FakeScenario.VALIDATION_ERROR

    await bot.say("confirmo")

    (result,) = _tool_results(model)
    assert result["error"] == "validation"
    assert "reglas de negocio" in result["message"]
    assert bot.messaging.statuses == []


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        ({"event_date": "2026-10-09"}, "posterior a hoy"),
        ({"event_date": "15/11/2026"}, "formato"),
        ({"district": "Miraflores"}, "Lima o Callao"),
        ({"address": "Av"}, "dirección"),
        ({"full_name": "A"}, "nombre"),
        ({"client_provides_mobility": "si"}, "verdadero o falso"),
        ({"package_id": "no-es-uuid"}, "formato"),
        ({"theme_id": str(SAFARI.id), "package_id": str(PREMIUM.id)}, None),
        ({"theme_id": None}, "temática"),
        ({"package_id": "00000000-0000-0000-0000-000000000000"}, "paquete"),
        (
            {"extras": [{"extra_id": "00000000-0000-0000-0000-000000000000", "quantity": 1}]},
            "extras",
        ),
    ],
)
async def test_invalid_quote_arguments_are_returned_to_the_model(
    change: dict[str, Any], fragment: str | None
) -> None:
    bot, model = _agent_bot(call("create_quote", **{**QUOTE_ARGS, **change}), say("ok"))

    await bot.say("confirmo")

    (result,) = _tool_results(model)
    if fragment is None:  # Safari sí es compatible con Premium: la cotización se crea
        assert result["ok"] is True
        return
    assert result["ok"] is False
    assert fragment in result["message"]
    assert "resumen de tu cotización" not in "".join(bot.sent)


async def test_an_incompatible_theme_is_rejected_before_creating_the_quote() -> None:
    basic = {**QUOTE_ARGS, "package_id": str(BASIC.id), "theme_id": str(SAFARI.id)}
    bot, model = _agent_bot(call("create_quote", **basic), say("ok"))

    await bot.say("confirmo")

    (result,) = _tool_results(model)
    assert "no es compatible" in result["message"]


async def test_expired_and_invalid_quote_states_are_tool_results_for_the_payment() -> None:
    bot, model = _agent_bot(
        call("create_quote", **QUOTE_ARGS),
        say("Cotizado."),
        call("pay_advance"),
        say("La cotización venció."),
    )
    await bot.say("confirmo")
    bot.pay_advance.scenario = FakeScenario.QUOTE_EXPIRED

    await bot.say("pagar")

    (_, expired) = _tool_results(model)[-2:]
    assert expired == {"ok": False, "error": "quote_expired"}
    assert (await _agent_session(bot)).payment_started is False
    assert "Yape" not in "".join(bot.sent)


async def test_paying_without_a_quote_or_twice_never_calls_the_port_again() -> None:
    bot, model = _agent_bot(
        call("pay_advance"),
        say("Primero cotizamos."),
        call("create_quote", **QUOTE_ARGS),
        say("Cotizado."),
        call("pay_advance"),
        say("Pago iniciado."),
        call("pay_advance"),
        say("Ya estaba iniciado."),
    )

    await bot.say("quiero pagar")
    assert _tool_results(model) == [{"ok": False, "error": "no_quote"}]
    await bot.say("confirmo")
    await bot.say("pagar")
    instructions = [body for body in bot.sent if "Yape" in body]
    await bot.say("pagar de nuevo")

    assert _tool_results(model)[-1]["already_started"] is True
    assert [body for body in bot.sent if "Yape" in body] == instructions


async def test_a_message_with_only_an_attachment_after_paying_gets_the_receipt_text() -> None:
    bot, model = _agent_bot(
        call("create_quote", **QUOTE_ARGS),
        say("Cotizado."),
        call("pay_advance"),
        say("Envía tu comprobante."),
    )
    await bot.run("confirmo", "pagar")
    calls_before = len(model.calls)

    reply = await bot.say("")

    assert reply == texts.RECEIPT_RECEIVED
    assert len(model.calls) == calls_before


async def test_an_attachment_before_paying_reaches_the_model_as_a_placeholder() -> None:
    bot, model = _agent_bot(say("¿Puedes escribirme tu consulta?"))

    await bot.say("")

    assert model.calls[0].messages[-1].content == ATTACHMENT_PLACEHOLDER


async def test_bad_tool_arguments_and_unknown_tools_are_reported_to_the_model() -> None:
    bot, model = _agent_bot(
        raw_call("create_quote", "{no es json"),
        raw_call("borrar_todo", "{}"),
        raw_call("create_quote", "[1]"),
        say("Disculpa."),
    )

    await bot.say("hola")

    results = _tool_results(model)
    assert results[0]["error"] == "invalid_arguments"
    assert results[1] == {"ok": False, "error": "unknown_tool"}
    assert results[2]["error"] == "invalid_arguments"


# --- Derivación ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("reason", "text"),
    [
        ("CLIENT_REQUEST", texts.HANDOFF_REQUESTED),
        ("BOT_NOT_UNDERSTOOD", texts.HANDOFF_NOT_UNDERSTOOD),
    ],
)
async def test_the_handoff_tool_hands_the_conversation_to_a_person(reason: str, text: str) -> None:
    bot, model = _agent_bot(call("request_handoff", reason=reason))

    reply = await bot.say("no entiendo nada de esto")

    assert reply == text
    assert bot.messaging.statuses == [(CONVERSATION_ID, ConversationStatus.HUMAN)]
    assert await bot.sessions.get(CONVERSATION_ID) is None
    assert len(model.calls) == 1  # no se pide otra respuesta al modelo


async def test_the_handoff_keyword_is_still_deterministic_and_skips_the_model() -> None:
    bot, model = _agent_bot()

    reply = await bot.say("quiero hablar con un asesor")

    assert reply == texts.HANDOFF_REQUESTED
    assert model.calls == []
    assert bot.messaging.statuses == [(CONVERSATION_ID, ConversationStatus.HUMAN)]


async def test_after_a_handoff_the_bot_stays_silent() -> None:
    bot, model = _agent_bot(call("request_handoff", reason="CLIENT_REQUEST"))
    await bot.say("necesito ayuda")

    reply = await bot.say("hola?", status=ConversationStatus.HUMAN)

    assert reply == ""
    assert bot.last_outcome is GatewayEventOutcome.IGNORED
    assert len(model.calls) == 1


async def test_the_tool_loop_is_bounded_and_ends_in_a_handoff() -> None:
    bot, model = _agent_bot(
        *[call("list_catalog", call_id=f"c{i}") for i in range(MAX_TOOL_ITERATIONS + 3)]
    )

    reply = await bot.say("hola")

    assert len(model.calls) == MAX_TOOL_ITERATIONS
    assert reply == texts.HANDOFF_NOT_UNDERSTOOD
    assert bot.messaging.statuses == [(CONVERSATION_ID, ConversationStatus.HUMAN)]
    assert await bot.sessions.get(CONVERSATION_ID) is None


async def test_an_unexpected_tool_error_hands_off_with_a_bot_error_and_no_content_in_logs() -> None:
    class Exploding:
        async def execute(self, dto: Any) -> Any:
            raise RuntimeError("clave secreta de la base de datos")

    bot, _ = _agent_bot(call("create_quote", **QUOTE_ARGS))
    bot.create_quote_override = Exploding()

    with capture_logs() as logs:
        reply = await bot.say("confirmo")

    assert reply == texts.HANDOFF_ERROR
    assert bot.messaging.statuses == [(CONVERSATION_ID, ConversationStatus.HUMAN)]
    assert [log for log in logs if log["event"] == "bot_turn_failed"][0]["step"] == "agent"
    assert "clave secreta" not in str(logs)


# --- Respaldo cuando falla el modelo ---------------------------------------------------------


@pytest.mark.parametrize("reason", ["timeout", "rate_limit", "connection", "api_error"])
async def test_a_model_failure_falls_back_to_the_menu_and_logs_only_the_reason(
    reason: str,
) -> None:
    bot, model = _agent_bot(LanguageModelError(reason))

    with capture_logs() as logs:
        reply = await bot.say("quiero una cotización con datos privados 999")

    assert reply.startswith("Hola, te damos la bienvenida a EventPro")
    fallback = [log for log in logs if log["event"] == "bot_llm_fallback"]
    assert len(fallback) == 1
    assert fallback[0]["reason"] == reason
    assert fallback[0]["conversation_id"] == CONVERSATION_ID
    assert "datos privados" not in str(logs)
    stored = await bot.sessions.get(CONVERSATION_ID)
    session = BotSession.from_dict(stored or {})
    assert session is not None
    assert session.step is BotStep.CATEGORY


async def test_a_conversation_that_fell_back_keeps_using_the_menu_until_menu_is_typed() -> None:
    bot, model = _agent_bot(LanguageModelError("timeout"), say("Bienvenido de nuevo."))
    await bot.say("hola")

    next_reply = await bot.say("3")
    assert "paquetes de Decoración" in next_reply
    assert len(model.calls) == 1  # el agente no volvió a intervenir

    back = await bot.say("menu")
    assert back == "Bienvenido de nuevo."
    assert (await _agent_session(bot)).history[-1].content == "Bienvenido de nuevo."


async def test_a_slow_model_exceeds_the_turn_budget_and_falls_back() -> None:
    class Slow:
        async def complete(self, **_: Any) -> LlmReply:
            await asyncio.sleep(1)
            return say("tarde")

    bot = BotHarness(model=Slow(), turn_budget_seconds=0.05)

    with capture_logs() as logs:
        reply = await bot.say("hola")

    assert reply.startswith("Hola, te damos la bienvenida")
    assert [log["reason"] for log in logs if log["event"] == "bot_llm_fallback"] == ["timeout"]


async def test_an_empty_model_reply_counts_as_a_failure() -> None:
    bot, _ = _agent_bot(LlmReply(text="  "))

    with capture_logs() as logs:
        reply = await bot.say("hola")

    assert reply.startswith("Hola, te damos la bienvenida")
    assert [log["reason"] for log in logs if log["event"] == "bot_llm_fallback"] == ["bad_response"]


async def test_a_model_failure_after_creating_the_quote_hands_off_instead_of_resetting() -> None:
    bot, _ = _agent_bot(call("create_quote", **QUOTE_ARGS), LanguageModelError("timeout"))

    with capture_logs() as logs:
        reply = await bot.say("confirmo")

    assert "resumen de tu cotización" in reply  # la cotización y su resumen ya se confirmaron
    assert reply.endswith(texts.HANDOFF_ERROR)
    assert bot.messaging.statuses == [(CONVERSATION_ID, ConversationStatus.HUMAN)]
    assert not [log for log in logs if log["event"] == "bot_llm_fallback"]


# --- Elegibilidad y duplicados ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "private"),
    [(ConversationStatus.HUMAN, False), (ConversationStatus.BOT, True)],
)
async def test_messages_the_bot_does_not_own_never_reach_the_model(
    status: ConversationStatus, private: bool
) -> None:
    bot, model = _agent_bot(say("no debería usarse"))

    reply = await bot.say("hola", status=status, private=private)

    assert reply == ""
    assert bot.last_outcome is GatewayEventOutcome.IGNORED
    assert model.calls == []


async def test_a_repeated_message_id_is_not_answered_twice() -> None:
    bot, model = _agent_bot(say("Hola."), say("Segunda respuesta."))
    await bot.say("hola", message_id="wamid-1")

    reply = await bot.say("hola", message_id="wamid-1")

    assert reply == ""
    assert bot.last_outcome is GatewayEventOutcome.IGNORED
    assert len(model.calls) == 1


# --- Historial -------------------------------------------------------------------------------


def _history(turns: int) -> list[LlmMessage]:
    history: list[LlmMessage] = []
    for number in range(turns):
        history.append(LlmMessage(LlmRole.USER, f"u{number}"))
        history.append(LlmMessage(LlmRole.ASSISTANT, f"a{number}"))
    return history


def test_trimming_keeps_a_short_history_untouched() -> None:
    history = _history(3)

    assert trim_history(history) == history


def test_trimming_keeps_the_window_and_starts_on_a_client_message() -> None:
    history = _history(30)  # 60 mensajes

    trimmed = trim_history(history)

    assert len(trimmed) <= MAX_HISTORY_MESSAGES
    assert trimmed[0].role is LlmRole.USER
    assert trimmed[-1] == history[-1]


def test_trimming_never_leaves_a_tool_result_without_its_request() -> None:
    from app.application.dtos.language_model_dto import LlmToolCall

    history = [
        LlmMessage(LlmRole.USER, "u"),
        LlmMessage(LlmRole.ASSISTANT, "", (LlmToolCall("c1", "list_catalog", "{}"),)),
        LlmMessage(LlmRole.TOOL, "{}", tool_call_id="c1"),
        LlmMessage(LlmRole.ASSISTANT, "a"),
        LlmMessage(LlmRole.USER, "u2"),
        LlmMessage(LlmRole.ASSISTANT, "a2"),
    ]

    trimmed = trim_history(history, max_messages=4)  # el corte cae sobre TOOL

    assert [m.content for m in trimmed] == ["u2", "a2"]


async def test_a_long_conversation_is_stored_and_sent_within_the_window() -> None:
    bot, model = _agent_bot(*[say(f"respuesta {n}") for n in range(40)])

    for number in range(40):
        await bot.say(f"mensaje {number}")

    stored = await _agent_session(bot)
    assert len(stored.history) <= MAX_HISTORY_MESSAGES
    assert stored.history[0].role is LlmRole.USER
    assert all(len(c.messages) <= MAX_HISTORY_MESSAGES for c in model.calls)
    assert model.calls[-1].messages[-1].content == "mensaje 39"


def test_the_session_round_trips_and_is_not_confused_with_a_menu_session() -> None:
    session = AgentSession(
        history=[
            LlmMessage(LlmRole.USER, "hola"),
            LlmMessage(LlmRole.ASSISTANT, "¡Hola!"),
        ],
        quote_id="q-1",
        payment_started=True,
        last_message_id="m1",
    )

    restored = AgentSession.from_dict(session.to_dict())

    assert restored == session
    assert BotSession.from_dict(session.to_dict()) is None
    assert AgentSession.from_dict(BotSession().to_dict()) is None
    assert AgentSession.from_dict({"engine": "agent", "history": [{"role": "???"}]}) is None
