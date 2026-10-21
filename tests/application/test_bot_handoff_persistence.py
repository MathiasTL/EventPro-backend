"""Derivación persistente y vínculo de cotización en ambos motores (spec 09, 6.2 y B8)."""

from typing import Any
from uuid import uuid4

import pytest
from structlog.testing import capture_logs

from app.application.dtos.conversation_event_dto import ConversationEvent
from app.application.dtos.language_model_dto import LlmMessage, LlmRole
from app.application.ports.output.language_model_port import LanguageModelError
from app.application.use_cases.bot import agent_prompt
from app.application.use_cases.bot import bot_messages as texts
from app.application.use_cases.bot.agent_engine import MAX_TOOL_ITERATIONS
from app.domain.entities.conversation_link import ConversationLink, HandoffReason
from app.infrastructure.adapters.secondary.external_services.fake_quote_use_cases import (
    FakeScenario,
)
from tests.application.agent_support import ScriptedLanguageModel, call, say
from tests.application.bot_support import CONVERSATION_ID, HAPPY_PATH, BotHarness
from tests.application.test_conversation_agent import QUOTE_ARGS

DETAILS = "Decoración Premium, Selva, 15/11/2026, Lima"


def _link(bot: BotHarness) -> ConversationLink:
    return bot.links.links[CONVERSATION_ID]


def _events(bot: BotHarness, name: str) -> list[ConversationEvent]:
    return [event for event in bot.publisher.events if event.event.value == name]


def _agent_bot(*steps: Any) -> BotHarness:
    return BotHarness(model=ScriptedLanguageModel(list(steps)))


def _assert_handed_off(bot: BotHarness, reason: HandoffReason) -> ConversationLink:
    link = _link(bot)
    assert link.handoff_reason is reason
    assert link.handed_off_at == bot.clock.utcnow()
    assert link.assigned_user_id is None
    (handoff,) = _events(bot, "handoff.requested")
    assert handoff.data["handoff_reason"] == reason.value
    assert handoff.data["handoff_summary"] == link.handoff_summary
    assert handoff.data["chatwoot_conversation_id"] == CONVERSATION_ID
    assert handoff.data["client"]["phone"] == "+51999111222"
    (updated,) = _events(bot, "conversation.updated")
    assert updated.data["mode"] == "HUMAN"
    assert updated.data["handoff_reason"] == reason.value
    return link


# --- Motor de menús ----------------------------------------------------------------------------


async def test_the_menu_keyword_records_the_handoff_with_the_structured_summary() -> None:
    bot = BotHarness()
    await bot.run(*HAPPY_PATH)  # la cotización ya se creó y espera el pago

    await bot.say("asesor")

    link = _assert_handed_off(bot, HandoffReason.CLIENT_REQUEST)
    assert link.handoff_summary is not None
    assert link.handoff_summary.endswith(f": {DETAILS}")
    assert link.handoff_summary.startswith("Cotización ")
    assert "Larco" not in link.handoff_summary
    assert "Ana" not in link.handoff_summary


async def test_two_not_understood_answers_record_bot_not_understood_without_client_text() -> None:
    bot = BotHarness()
    await bot.run("hola", "xyz secreto", "tampoco")

    link = _assert_handed_off(bot, HandoffReason.BOT_NOT_UNDERSTOOD)
    assert link.handoff_summary is None  # aún no había datos de la solicitud
    assert "secreto" not in str(_events(bot, "handoff.requested")[0].data)


async def test_choosing_a_person_in_the_alternatives_menu_records_a_client_request() -> None:
    bot = BotHarness()
    bot.create_quote.scenario = FakeScenario.AVAILABILITY_CONFLICT
    await bot.run(*HAPPY_PATH)  # la cotización se rechaza y se ofrecen alternativas
    await bot.say("3")  # «Hablar con una persona»

    link = _assert_handed_off(bot, HandoffReason.CLIENT_REQUEST)
    assert link.handoff_summary == f"Sin cotización: {DETAILS}"


async def test_an_empty_catalog_records_a_bot_error() -> None:
    from tests.application.bot_support import FakeCatalog

    bot = BotHarness(catalog=FakeCatalog(packages=()))

    await bot.say("hola")

    _assert_handed_off(bot, HandoffReason.BOT_ERROR)


async def test_an_unexpected_menu_error_records_a_bot_error() -> None:
    class Exploding:
        async def execute(self, dto: Any) -> Any:
            raise RuntimeError("falla")

    bot = BotHarness()
    await bot.run(*HAPPY_PATH[:-1])
    bot.create_quote_override = Exploding()

    await bot.say("no")

    link = _assert_handed_off(bot, HandoffReason.BOT_ERROR)
    assert link.quote_id is None


# --- Agente --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tool_reason", "expected"),
    [
        ("CLIENT_REQUEST", HandoffReason.CLIENT_REQUEST),
        ("BOT_NOT_UNDERSTOOD", HandoffReason.BOT_NOT_UNDERSTOOD),
    ],
)
async def test_the_handoff_tool_records_the_mapped_reason(
    tool_reason: str, expected: HandoffReason
) -> None:
    bot = _agent_bot(call("request_handoff", reason=tool_reason))

    await bot.say("necesito ayuda")

    _assert_handed_off(bot, expected)


async def test_the_agent_keyword_records_the_summary_of_the_agent_quote() -> None:
    bot = _agent_bot(call("create_quote", **QUOTE_ARGS), say("Listo."))
    await bot.say("confirmo")
    quote_id = _link(bot).quote_id
    assert quote_id is not None

    await bot.say("asesor")

    link = _assert_handed_off(bot, HandoffReason.CLIENT_REQUEST)
    assert link.handoff_summary == f"Cotización {str(quote_id)[:8]}: {DETAILS}"


async def test_an_agent_tool_error_records_a_bot_error() -> None:
    class Exploding:
        async def execute(self, dto: Any) -> Any:
            raise RuntimeError("falla")

    bot = _agent_bot(call("create_quote", **QUOTE_ARGS))
    bot.create_quote_override = Exploding()

    await bot.say("confirmo")

    _assert_handed_off(bot, HandoffReason.BOT_ERROR)


async def test_a_model_failure_after_the_quote_records_a_bot_error_with_the_quote() -> None:
    bot = _agent_bot(call("create_quote", **QUOTE_ARGS), LanguageModelError("timeout"))

    await bot.say("confirmo")

    link = _assert_handed_off(bot, HandoffReason.BOT_ERROR)
    assert link.quote_id is not None
    assert link.handoff_summary == f"Cotización {str(link.quote_id)[:8]}: {DETAILS}"


async def test_the_tool_loop_limit_records_bot_not_understood() -> None:
    bot = _agent_bot(
        *[call(agent_prompt.LIST_CATALOG, call_id=f"c{i}") for i in range(MAX_TOOL_ITERATIONS)]
    )

    await bot.say("hola")

    _assert_handed_off(bot, HandoffReason.BOT_NOT_UNDERSTOOD)


# --- Falla de Chatwoot, asignado viejo y mejor esfuerzo --------------------------------------


@pytest.mark.parametrize("engine", ["menu", "agent"])
async def test_a_chatwoot_failure_records_nothing_but_still_answers_the_client(
    engine: str,
) -> None:
    bot = BotHarness() if engine == "menu" else _agent_bot()
    bot.messaging.fail = True

    reply = await bot.say("asesor")

    assert reply == texts.HANDOFF_REQUESTED
    assert CONVERSATION_ID not in bot.links.links
    assert bot.publisher.events == []


async def test_a_stale_assignee_is_cleared_at_the_handoff() -> None:
    bot = BotHarness()
    await bot.say("hola")
    stale = uuid4()
    await bot.links.ensure(CONVERSATION_ID, None, bot.clock.utcnow())
    assert await bot.links.claim(CONVERSATION_ID, stale, None)

    await bot.say("asesor")

    assert _link(bot).assigned_user_id is None
    _assert_handed_off(bot, HandoffReason.CLIENT_REQUEST)


async def test_a_lost_release_is_logged_and_the_new_owner_is_kept() -> None:
    bot = BotHarness()
    old, new = uuid4(), uuid4()
    await bot.links.ensure(CONVERSATION_ID, None, bot.clock.utcnow())
    assert await bot.links.claim(CONVERSATION_ID, old, None)
    bot.handoff_link_uow.racing_assignee = new  # una toma ganó en el instante

    with capture_logs() as logs:
        await bot.say("asesor")

    assert _link(bot).assigned_user_id == new
    assert any(log["event"] == "bot_handoff_release_cas_lost" for log in logs)


async def test_publish_and_persistence_failures_never_break_the_reply() -> None:
    bot = BotHarness()
    bot.publisher.error = RuntimeError("redis caido")

    with capture_logs() as logs:
        reply = await bot.say("asesor")

    assert reply == texts.HANDOFF_REQUESTED
    assert _link(bot).handoff_reason is HandoffReason.CLIENT_REQUEST
    assert any(log["event"] == "bot_handoff_publish_failed" for log in logs)

    broken = BotHarness()

    broken.handoff_link_uow.fail = True
    with capture_logs() as logs:
        reply = await broken.say("asesor")

    assert reply == texts.HANDOFF_REQUESTED
    assert any(log["event"] == "bot_handoff_record_failed" for log in logs)


# --- Vínculo de la cotización -----------------------------------------------------------------


async def test_the_menu_links_the_quote_in_the_same_transaction_as_the_quote() -> None:
    bot = BotHarness()

    await bot.run(*HAPPY_PATH[:-1])
    assert CONVERSATION_ID not in bot.links.links  # aún no hay cotización

    await bot.say(HAPPY_PATH[-1])

    link = _link(bot)
    (quote,) = bot.quotes.quotes()
    assert link.quote_id == quote.id
    assert link.client_id is not None


async def test_the_agent_links_the_quote_and_the_most_recent_quote_wins() -> None:
    bot = _agent_bot(
        call("create_quote", **QUOTE_ARGS),
        say("Listo."),
        call("create_quote", **{**QUOTE_ARGS, "event_date": "2026-11-20"}),
        say("Otra."),
    )

    await bot.say("confirmo")
    first = _link(bot).quote_id
    await bot.say("mejor el 20")

    assert first is not None
    assert _link(bot).quote_id not in (None, first)
    assert _link(bot).quote_id is not None


@pytest.mark.parametrize("engine", ["menu", "agent"])
async def test_the_quote_link_rolls_back_with_the_quote_transaction(
    engine: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*_: Any) -> str:
        raise RuntimeError("falla al armar el resumen")

    if engine == "menu":
        bot = BotHarness()
        await bot.run(*HAPPY_PATH[:-1])
        monkeypatch.setattr(texts, "quote_summary", explode)
        await bot.say("no")
    else:
        bot = _agent_bot(call("create_quote", **QUOTE_ARGS))
        monkeypatch.setattr(texts, "quote_summary", explode)
        await bot.say("confirmo")

    assert _link(bot).quote_id is None  # solo existe el vínculo de la derivación
    _assert_handed_off(bot, HandoffReason.BOT_ERROR)


def test_the_agent_session_round_trips_the_quote_details() -> None:
    from app.application.use_cases.bot.agent_session import AgentSession

    session = AgentSession(
        history=[LlmMessage(LlmRole.USER, "hola")], quote_id="q1", quote_details=DETAILS
    )

    restored = AgentSession.from_dict(session.to_dict())

    assert restored is not None
    assert restored.quote_details == DETAILS
