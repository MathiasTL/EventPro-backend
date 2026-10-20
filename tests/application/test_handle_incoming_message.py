"""HandleIncomingMessage: el flujo del bot de WhatsApp, sus errores y la derivación."""

import re
from datetime import date, time
from decimal import Decimal
from typing import Any

import pytest
from structlog.testing import capture_logs

from app.application.dtos.gateway_event_dto import GatewayEventOutcome
from app.application.dtos.messaging_dto import ConversationStatus
from app.application.dtos.quote_dto import CreatedQuoteDTO, CreateQuoteInput
from app.application.use_cases.bot import bot_messages as texts
from app.application.use_cases.bot.bot_session import BotSession, BotStep
from app.domain.entities.quote import QuoteStatus
from app.infrastructure.adapters.secondary.external_services.fake_quote_use_cases import (
    FakeScenario,
)
from tests.application.bot_support import (
    CONVERSATION_ID,
    HAPPY_PATH,
    PHONE,
    BotHarness,
    FakeCatalog,
    FakeLock,
)

VOSEO = re.compile(
    r"\b(vos|tenés|tenes|podés|podes|elegí|elegi|escribí|escribi|hacé|mandá|decime|querés|sabés)\b",
    re.IGNORECASE,
)


async def _session(bot: BotHarness) -> BotSession:
    stored = await bot.sessions.get(CONVERSATION_ID)
    assert stored is not None
    session = BotSession.from_dict(stored)
    assert session is not None
    return session


# --- Camino feliz --------------------------------------------------------------------------


async def test_the_first_message_gets_a_greeting_and_the_real_categories() -> None:
    bot = BotHarness()

    reply = await bot.say("hola")

    assert reply.startswith("Hola, te damos la bienvenida a EventPro")
    assert "1. Shows\n2. DJ\n3. Decoración" in reply
    assert "Carpas" not in reply  # ninguna oferta activa de esa categoría
    assert (await _session(bot)).step is BotStep.CATEGORY


async def test_a_client_can_quote_and_pay_the_advance_end_to_end() -> None:
    bot = BotHarness()

    summary = await bot.run(*HAPPY_PATH)

    assert "Paquete: Decoración Premium" in summary
    assert "Temática: Selva" in summary
    assert "Extras: Fotografía, Globos" in summary
    assert "Fecha: 15/11/2026 a las 16:30" in summary
    assert "Lugar: Av. Larco 123, frente al parque, Lima" in summary
    assert "Servicios: S/ 1,000.00" in summary
    assert "Movilidad: S/ 80.50" in summary
    assert "Total: S/ 1,080.50" in summary
    assert "Adelanto para reservar: S/ 100.00" in summary
    assert "Saldo de servicios, el día del evento: S/ 900.00" in summary
    assert "válida hasta el 08/10/2026 10:00 (24 horas)" in summary
    assert "solo queda reservada cuando validemos el pago del adelanto" in summary
    assert "1. Pagar adelanto" in summary
    assert "Yape" not in summary  # los datos de pago salen solo tras iniciar el pago

    (quote,) = bot.quotes.quotes()
    assert quote.status is QuoteStatus.SENT
    assert quote.event_date == date(2026, 11, 15)
    assert quote.event_time == time(16, 30)
    assert quote.location_district == "Lima"
    assert len(quote.extras) == 2
    assert quote.theme_id is not None
    (client,) = bot.quotes.clients()
    assert (client.phone, client.full_name) == (PHONE.value, "Ana Torres Quispe")

    payment = await bot.say("1")

    assert quote.status is QuoteStatus.PAYMENT_STARTED
    assert "paga el adelanto de S/ 100.00" in payment
    assert "Yape: +51900111222" in payment
    assert "Transferencia BCP" in payment
    assert (await _session(bot)).step is BotStep.PAID


async def test_the_quote_summary_is_enqueued_in_the_same_transaction_as_the_quote() -> None:
    bot = BotHarness()
    await bot.run(*HAPPY_PATH[:-1])
    commits_before = bot.outbox.commits

    await bot.say("no")

    assert bot.outbox.commits == commits_before + 1
    assert len(bot.quotes.quotes()) == 1
    assert "resumen de tu cotización" in bot.sent[-1]


async def test_only_text_messages_are_enqueued_to_the_client_phone() -> None:
    bot = BotHarness()
    await bot.run(*HAPPY_PATH)

    assert {m.recipient for m in bot.outbox.messages.values()} == {PHONE}
    assert {m.message_type.value for m in bot.outbox.messages.values()} == {"TEXT"}


async def test_no_bot_text_uses_voseo() -> None:
    bot = BotHarness()
    await bot.run(*HAPPY_PATH, "1")
    await bot.say("xyz")  # no entendido
    await bot.say("menu")

    assert bot.sent
    for body in bot.sent:
        assert VOSEO.search(body) is None, body


# --- Menús: número o título ----------------------------------------------------------------


@pytest.mark.parametrize("answer", ["2", "dj", "DJ", "  Dj!  "])
async def test_a_category_can_be_chosen_by_number_or_title(answer: str) -> None:
    bot = BotHarness()
    await bot.run("hola", answer)

    session = await _session(bot)
    assert session.step is BotStep.PACKAGE
    assert session.category == "DJ"


async def test_titles_are_matched_ignoring_case_and_accents() -> None:
    bot = BotHarness()

    reply = await bot.run("hola", "decoracion", "decoración premium")

    assert (await _session(bot)).package_name == "Decoración Premium"
    assert "1. Selva" in reply and "2. Safari" in reply
    assert "Retirada" not in reply  # una temática inactiva no se ofrece


async def test_the_package_menu_only_lists_the_chosen_category_with_prices() -> None:
    bot = BotHarness()

    reply = await bot.run("hola", "3")

    assert "paquetes de Decoración" in reply
    assert "1. Decoración Básica - S/ 400.00" in reply
    assert "2. Decoración Premium - S/ 900.00" in reply
    assert "DJ Fiesta" not in reply


async def test_a_package_without_compatible_themes_skips_the_theme_step() -> None:
    bot = BotHarness()

    reply = await bot.run("hola", "2", "1")

    assert (await _session(bot)).step is BotStep.EXTRAS
    assert "extras" in reply


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("1", ["Fotografía"]),
        ("1,2", ["Fotografía", "Globos"]),
        ("1 2", ["Fotografía", "Globos"]),
        ("1 y 2", ["Fotografía", "Globos"]),
        ("globos", ["Globos"]),
        ("2, 2", ["Globos"]),
        ("0", []),
        ("no", []),
    ],
)
async def test_extras_accept_several_choices_or_none(answer: str, expected: list[str]) -> None:
    bot = BotHarness()
    await bot.run("hola", "2", "1", answer)

    session = await _session(bot)
    assert session.step is BotStep.DATE
    assert [extra.title for extra in session.extras] == expected


async def test_without_extras_in_the_catalog_the_step_is_skipped() -> None:
    bot = BotHarness(catalog=FakeCatalog(extras=()))

    reply = await bot.run("hola", "2", "1")

    assert (await _session(bot)).step is BotStep.DATE
    assert "DD/MM/AAAA" in reply


async def test_the_mobility_question_accepts_yes_and_no() -> None:
    bot = BotHarness()
    await bot.run(*HAPPY_PATH[:10])
    assert (await _session(bot)).step is BotStep.MOBILITY

    await bot.say("sí")

    session = await _session(bot)
    assert session.provides_mobility is True
    assert session.step is BotStep.OBSERVATIONS


async def test_providing_the_mobility_shows_it_as_the_clients_responsibility() -> None:
    bot = BotHarness()
    await bot.run(*HAPPY_PATH[:10])
    await bot.say("Yo proveo la movilidad")

    summary = await bot.say("Que llegue puntual")

    assert "Movilidad: a tu cargo" in summary
    (quote,) = bot.quotes.quotes()
    assert quote.final_mobility_amount == Decimal("0.00")
    assert quote.observations == "Que llegue puntual"


# --- Validación de entradas ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("answer", "hint"),
    [
        ("mañana", "formato DD/MM/AAAA"),
        ("31/02/2026", "formato DD/MM/AAAA"),
        ("01/01/2020", "posterior a hoy"),
        ("09/10/2026", "posterior a hoy"),  # hoy en Lima
    ],
)
async def test_an_invalid_or_past_date_is_asked_again_with_a_hint(answer: str, hint: str) -> None:
    bot = BotHarness()
    await bot.run(*HAPPY_PATH[:5])

    reply = await bot.say(answer)

    assert reply.startswith(f"{texts.NOT_UNDERSTOOD} ")
    assert hint in reply
    assert (await _session(bot)).step is BotStep.DATE


@pytest.mark.parametrize("answer", ["tarde", "25:00", "16:75", "4pm"])
async def test_an_invalid_time_is_asked_again(answer: str) -> None:
    bot = BotHarness()
    await bot.run(*HAPPY_PATH[:6])

    reply = await bot.say(answer)

    assert "HH:MM" in reply
    assert (await _session(bot)).step is BotStep.TIME


@pytest.mark.parametrize(("step_answers", "bad"), [(7, "x"), (8, "ok"), (9, "12345")])
async def test_short_or_unmatched_answers_repeat_the_same_question(
    step_answers: int, bad: str
) -> None:
    bot = BotHarness()
    await bot.run(*HAPPY_PATH[:step_answers])
    before = (await _session(bot)).step

    reply = await bot.say(bad)

    assert reply.startswith(texts.NOT_UNDERSTOOD)
    assert (await _session(bot)).step is before


async def test_a_valid_answer_resets_the_not_understood_counter() -> None:
    bot = BotHarness()
    await bot.run("hola", "xyz")
    assert (await _session(bot)).misses == 1

    await bot.say("2")
    await bot.say("xyz")

    assert (await _session(bot)).misses == 1
    assert bot.messaging.statuses == []


# --- Reglas de quién responde ---------------------------------------------------------------


@pytest.mark.parametrize("private", [False, True])
async def test_a_conversation_not_in_pending_is_ignored(private: bool) -> None:
    bot = BotHarness()

    reply = await bot.say("hola", status=ConversationStatus.HUMAN, private=private)

    assert reply == ""
    assert bot.last_outcome is GatewayEventOutcome.IGNORED
    assert await bot.sessions.get(CONVERSATION_ID) is None


async def test_a_private_note_is_ignored_even_in_a_pending_conversation() -> None:
    bot = BotHarness()

    reply = await bot.say("nota interna", private=True)

    assert reply == ""
    assert bot.last_outcome is GatewayEventOutcome.IGNORED


async def test_the_same_message_is_never_answered_twice() -> None:
    bot = BotHarness()
    await bot.say("hola", message_id="77")
    await bot.say("3", message_id="78")
    sent = len(bot.sent)

    reply = await bot.say("3", message_id="78")

    assert reply == ""
    assert len(bot.sent) == sent
    assert bot.last_outcome is GatewayEventOutcome.IGNORED
    assert (await _session(bot)).step is BotStep.PACKAGE


async def test_a_conversation_busy_with_another_message_is_skipped() -> None:
    lock = FakeLock(available=False)
    bot = BotHarness(lock=lock)

    reply = await bot.say("hola")

    assert reply == ""
    assert bot.last_outcome is GatewayEventOutcome.IGNORED
    assert lock.events == ["denied"]


async def test_the_conversation_lock_is_released_even_when_the_turn_fails() -> None:
    lock = FakeLock()
    bot = BotHarness(lock=lock)

    await bot.say("hola")

    assert lock.events == ["acquire", "release"]


async def test_a_message_with_only_attachments_starts_the_conversation() -> None:
    bot = BotHarness()

    reply = await bot.say("")

    assert "bienvenida" in reply


# --- Reiniciar -----------------------------------------------------------------------------


@pytest.mark.parametrize("word", ["reiniciar", "menu", "Menú", "inicio"])
async def test_restart_words_begin_again_from_any_step(word: str) -> None:
    bot = BotHarness()
    await bot.run(*HAPPY_PATH[:7])

    reply = await bot.say(word)

    assert "bienvenida" in reply
    session = await _session(bot)
    assert session.step is BotStep.CATEGORY
    assert session.package_id is None and session.event_date is None


# --- Derivación a un encargado (US-27) -----------------------------------------------------


@pytest.mark.parametrize(
    "request_text",
    ["asesor", "Quiero hablar con un encargado", "necesito un HUMANO", "¿Me pasas con un asesor?"],
)
async def test_asking_for_a_person_hands_the_conversation_off(request_text: str) -> None:
    bot = BotHarness()
    await bot.run(*HAPPY_PATH[:5])

    reply = await bot.say(request_text)

    assert reply == texts.HANDOFF_REQUESTED
    assert bot.messaging.statuses == [(CONVERSATION_ID, ConversationStatus.HUMAN)]
    assert await bot.sessions.get(CONVERSATION_ID) is None


async def test_the_handoff_keyword_works_before_the_first_menu() -> None:
    bot = BotHarness()

    reply = await bot.say("hola, quiero un asesor")

    assert reply == texts.HANDOFF_REQUESTED
    assert bot.messaging.statuses == [(CONVERSATION_ID, ConversationStatus.HUMAN)]


async def test_two_consecutive_not_understood_answers_hand_off() -> None:
    bot = BotHarness()
    await bot.run("hola", "no sé")
    assert bot.messaging.statuses == []

    reply = await bot.say("tampoco")

    assert reply == texts.HANDOFF_NOT_UNDERSTOOD
    assert bot.messaging.statuses == [(CONVERSATION_ID, ConversationStatus.HUMAN)]
    assert await bot.sessions.get(CONVERSATION_ID) is None


async def test_after_the_handoff_the_bot_stays_silent() -> None:
    bot = BotHarness()
    await bot.say("asesor")

    reply = await bot.say("hola?", status=ConversationStatus.HUMAN)

    assert reply == ""
    assert bot.last_outcome is GatewayEventOutcome.IGNORED


async def test_a_failing_status_change_still_clears_the_session_and_tells_the_client() -> None:
    bot = BotHarness()
    bot.messaging.fail = True

    with capture_logs() as logs:
        reply = await bot.say("asesor")

    assert reply == texts.HANDOFF_REQUESTED
    assert await bot.sessions.get(CONVERSATION_ID) is None
    assert any(log["event"] == "bot_handoff_status_failed" for log in logs)


async def test_an_empty_catalog_hands_off_instead_of_showing_an_empty_menu() -> None:
    bot = BotHarness(catalog=FakeCatalog(packages=()))

    reply = await bot.say("hola")

    assert reply == texts.HANDOFF_NO_CATALOG
    assert bot.messaging.statuses == [(CONVERSATION_ID, ConversationStatus.HUMAN)]


# --- Reacciones a los errores de la spec 08, sección 2.3 -----------------------------------


async def _until_summary_turn(bot: BotHarness) -> None:
    await bot.run(*HAPPY_PATH[:-1])


async def test_an_availability_rejection_offers_alternatives_and_a_person() -> None:
    bot = BotHarness()
    bot.create_quote.scenario = FakeScenario.AVAILABILITY_CONFLICT
    await _until_summary_turn(bot)

    reply = await bot.say("no")

    assert "no están disponibles" in reply
    assert "1. 15/10/2026 a las 18:00" in reply
    assert "2. Elegir otra fecha u horario" in reply
    assert "3. Hablar con un encargado" in reply
    assert bot.quotes.quotes() == []
    assert (await _session(bot)).step is BotStep.ALTERNATIVES


async def test_picking_an_alternative_creates_the_quote_for_that_slot() -> None:
    bot = BotHarness()
    bot.create_quote.scenario = FakeScenario.SIMULTANEOUS_THRESHOLD
    await _until_summary_turn(bot)
    await bot.say("no")
    bot.create_quote.scenario = FakeScenario.OK

    reply = await bot.say("1")

    assert "Fecha: 15/10/2026 a las 18:00" in reply
    (quote,) = bot.quotes.quotes()
    assert (quote.event_date, quote.event_time) == (date(2026, 10, 15), time(18, 0))
    assert (await _session(bot)).step is BotStep.CONFIRM


async def test_choosing_another_date_asks_only_for_the_date_and_time() -> None:
    bot = BotHarness()
    bot.create_quote.scenario = FakeScenario.AVAILABILITY_CONFLICT
    await _until_summary_turn(bot)
    await bot.say("no")
    bot.create_quote.scenario = FakeScenario.OK

    assert "DD/MM/AAAA" in await bot.say("elegir otra fecha u horario")
    assert "HH:MM" in await bot.say("20/11/2026")
    summary = await bot.say("19:00")

    assert "Fecha: 20/11/2026 a las 19:00" in summary
    assert "Lugar: Av. Larco 123, frente al parque, Lima" in summary
    assert len(bot.quotes.quotes()) == 1


async def test_choosing_the_person_in_the_alternatives_menu_hands_off() -> None:
    bot = BotHarness()
    bot.create_quote.scenario = FakeScenario.AVAILABILITY_CONFLICT
    await _until_summary_turn(bot)
    await bot.say("no")

    reply = await bot.say("3")

    assert reply == texts.HANDOFF_REQUESTED
    assert bot.messaging.statuses == [(CONVERSATION_ID, ConversationStatus.HUMAN)]


async def test_a_payment_rejected_for_availability_also_offers_alternatives() -> None:
    bot = BotHarness()
    await bot.run(*HAPPY_PATH)
    bot.pay_advance.scenario = FakeScenario.AVAILABILITY_CONFLICT
    # Vuelve al paso de confirmación para pagar de nuevo.
    session = await _session(bot)
    session.step = BotStep.CONFIRM
    await bot.sessions.save(CONVERSATION_ID, session.to_dict())

    reply = await bot.say("1")

    assert "no están disponibles" in reply
    assert "Yape" not in reply  # no se revelan datos de pago


@pytest.mark.parametrize(
    ("scenario", "message"),
    [
        (FakeScenario.QUOTE_EXPIRED, texts.QUOTE_EXPIRED),
        (FakeScenario.INVALID_QUOTE_STATE, texts.QUOTE_UNAVAILABLE),
        (FakeScenario.QUOTE_NOT_FOUND, texts.QUOTE_UNAVAILABLE),
    ],
)
async def test_an_expired_or_invalid_quote_is_reported_without_payment_data(
    scenario: FakeScenario, message: str
) -> None:
    bot = BotHarness()
    await bot.run(*HAPPY_PATH)
    bot.pay_advance.scenario = scenario
    session = await _session(bot)
    session.step = BotStep.CONFIRM
    await bot.sessions.save(CONVERSATION_ID, session.to_dict())

    reply = await bot.say("pagar adelanto")

    assert reply == message
    assert bot.messaging.statuses == []


async def test_a_validation_error_asks_again_for_the_date() -> None:
    bot = BotHarness()
    bot.create_quote.scenario = FakeScenario.VALIDATION_ERROR
    await _until_summary_turn(bot)

    reply = await bot.say("no")

    assert reply.startswith(texts.INVALID_DATA)
    assert "DD/MM/AAAA" in reply
    assert (await _session(bot)).step is BotStep.DATE
    assert bot.messaging.statuses == []


class _ExplodingCreateQuote:
    async def execute(self, dto: CreateQuoteInput) -> CreatedQuoteDTO:
        raise RuntimeError("la base de datos no responde")


async def test_an_unexpected_error_hands_off_and_leaves_no_partial_message() -> None:
    bot = BotHarness()
    await _until_summary_turn(bot)
    bot.create_quote_override = _ExplodingCreateQuote()
    sent_before = len(bot.sent)

    with capture_logs() as logs:
        reply = await bot.say("no")

    assert reply == texts.HANDOFF_ERROR
    assert len(bot.sent) == sent_before + 1
    assert bot.messaging.statuses == [(CONVERSATION_ID, ConversationStatus.HUMAN)]
    assert await bot.sessions.get(CONVERSATION_ID) is None
    failed = [log for log in logs if log["event"] == "bot_turn_failed"]
    assert failed[0]["error_type"] == "RuntimeError"
    assert "base de datos" not in str(logs)  # el log no lleva el mensaje del error


async def test_a_paid_conversation_reminds_the_client_and_handles_receipts() -> None:
    bot = BotHarness()
    await bot.run(*HAPPY_PATH, "1")

    assert await bot.say("gracias") == texts.ALREADY_PAID
    assert await bot.say("") == texts.RECEIPT_RECEIVED


# --- Logs ----------------------------------------------------------------------------------


async def test_logs_never_carry_client_text_names_or_phones() -> None:
    bot = BotHarness()
    with capture_logs() as logs:
        await bot.run(*HAPPY_PATH)
        await bot.say("asesor")
        await bot.say("hola", status=ConversationStatus.HUMAN)

    dump: Any = str(logs)
    for secret in ("Ana Torres", "Larco", "999111222", "hola"):
        assert secret not in dump
