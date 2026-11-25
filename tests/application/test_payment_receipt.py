"""Comprobante de pago por WhatsApp en ambos motores: registro, derivación y errores."""

from typing import Any
from uuid import UUID

import pytest
from structlog.testing import capture_logs

from app.application.dtos.language_model_dto import LlmReply
from app.application.dtos.messaging_dto import ConversationStatus, MessageAttachment
from app.application.use_cases.bot import bot_messages as texts
from app.application.use_cases.bot.bot_handoff import map_reason, receipt_summary
from app.application.use_cases.bot.payment_receipt import first_receipt_attachment
from app.domain.entities.conversation_link import ConversationLink, HandoffReason
from app.domain.exceptions.messaging_exceptions import MessagingUnavailableError
from app.domain.exceptions.resource_exceptions import ResourceInUseError
from tests.application.agent_support import ScriptedLanguageModel, call, say
from tests.application.bot_support import (
    CONVERSATION_ID,
    HAPPY_PATH,
    INVALID_RECEIPT,
    MAX_RECEIPT_BYTES,
    BotHarness,
    add_receipt_file,
    receipt_attachment,
)
from tests.application.test_conversation_agent import QUOTE_ARGS


async def _menu_bot() -> BotHarness:
    """Cliente del motor de menús que ya inició el pago y debe enviar su comprobante."""

    bot = BotHarness()
    await bot.run(*HAPPY_PATH, "1")
    return bot


async def _agent_bot() -> BotHarness:
    model = ScriptedLanguageModel(
        [
            call("create_quote", **QUOTE_ARGS),
            say("Cotizado."),
            call("pay_advance"),
            say("Envía tu comprobante."),
        ]
    )
    bot = BotHarness(model=model)
    await bot.run("confirmo", "pagar")
    return bot


@pytest.fixture(params=["menu", "agent"])
async def paid_bot(request: pytest.FixtureRequest) -> BotHarness:
    return await (_menu_bot() if request.param == "menu" else _agent_bot())


def _link(bot: BotHarness) -> ConversationLink:
    return bot.links.links[CONVERSATION_ID]


def _quote_id(bot: BotHarness) -> UUID:
    quote_id = _link(bot).quote_id
    assert quote_id is not None
    return quote_id


def _handoffs(bot: BotHarness) -> list[Any]:
    return [e for e in bot.publisher.events if e.event.value == "handoff.requested"]


async def _send_receipt(bot: BotHarness, text: str = "") -> str:
    add_receipt_file(bot)
    return await bot.say(text, attachments=(receipt_attachment(),))


# --- Comprobante válido ----------------------------------------------------------------------


async def test_a_valid_receipt_registers_the_advance_and_hands_off(paid_bot: BotHarness) -> None:
    reply = await _send_receipt(paid_bot)

    assert reply == texts.RECEIPT_REGISTERED
    assert paid_bot.register_receipt.registered == [(_quote_id(paid_bot), "evidence/receipt-1.png")]
    assert paid_bot.storage.stored == {"evidence/receipt-1.png": b"\x89PNG-receipt"}
    link = _link(paid_bot)
    assert link.handoff_reason is HandoffReason.PAYMENT_RECEIPT
    assert link.handoff_summary is not None
    assert link.handoff_summary.endswith("Comprobante de pago recibido")
    assert link.handoff_summary.startswith("Cotización ")
    (handoff,) = _handoffs(paid_bot)
    assert handoff.data["handoff_reason"] == "PAYMENT_RECEIPT"
    assert paid_bot.messaging.statuses == [(CONVERSATION_ID, ConversationStatus.HUMAN)]
    assert await paid_bot.sessions.get(CONVERSATION_ID) is None


async def test_a_receipt_with_a_caption_is_still_a_receipt(paid_bot: BotHarness) -> None:
    await _send_receipt(paid_bot, "aquí está mi pago")

    assert len(paid_bot.register_receipt.registered) == 1
    assert _link(paid_bot).handoff_reason is HandoffReason.PAYMENT_RECEIPT


async def test_a_pdf_receipt_is_accepted_and_the_first_valid_attachment_wins(
    paid_bot: BotHarness,
) -> None:
    add_receipt_file(paid_bot, attachment_id=2)
    audio = receipt_attachment(1, file_type="audio", content_type="audio/ogg")
    pdf = receipt_attachment(2, file_type="file", content_type="application/pdf")

    await paid_bot.say("", attachments=(audio, pdf, receipt_attachment(3)))

    assert len(paid_bot.register_receipt.registered) == 1
    assert _link(paid_bot).handoff_reason is HandoffReason.PAYMENT_RECEIPT


async def test_the_log_of_a_registered_receipt_carries_no_file_or_text(
    paid_bot: BotHarness,
) -> None:
    with capture_logs() as logs:
        await _send_receipt(paid_bot, "texto secreto")

    assert "texto secreto" not in str(logs)
    assert "PNG-receipt" not in str(logs)


# --- Lo que no es un comprobante ---------------------------------------------------------------


async def test_a_message_without_attachment_is_not_a_receipt() -> None:
    bot = await _menu_bot()

    assert await bot.say("") == texts.ALREADY_PAID
    assert bot.register_receipt.registered == []
    assert bot.messaging.statuses == []


async def test_a_text_message_after_paying_still_reaches_the_agent() -> None:
    bot = await _agent_bot()
    model = bot.use_case._agent._model  # type: ignore[union-attr]
    model.steps.append(LlmReply(text="Con gusto."))

    assert await bot.say("¿cuándo me confirman?") == "Con gusto."
    assert bot.register_receipt.registered == []


async def test_the_first_message_of_a_client_with_an_attachment_is_not_a_receipt() -> None:
    bot = BotHarness()
    add_receipt_file(bot)

    reply = await bot.say("", attachments=(receipt_attachment(),))

    assert texts.RECEIPT_REGISTERED not in reply
    assert bot.register_receipt.registered == []


# --- Archivo inválido ----------------------------------------------------------------------------


async def test_an_invalid_file_asks_to_resend_and_registers_nothing(paid_bot: BotHarness) -> None:
    add_receipt_file(paid_bot, data=INVALID_RECEIPT)

    reply = await paid_bot.say("", attachments=(receipt_attachment(),))

    assert reply == texts.RECEIPT_UNREADABLE
    assert paid_bot.register_receipt.registered == []
    assert paid_bot.messaging.statuses == []
    assert _handoffs(paid_bot) == []
    # La sesión sigue esperando el comprobante y el siguiente archivo válido se registra.
    await _send_receipt(paid_bot)
    assert len(paid_bot.register_receipt.registered) == 1


async def test_an_oversized_file_is_rejected_without_downloading(paid_bot: BotHarness) -> None:
    paid_bot.messaging.download_error = AssertionError("no debía descargarse")
    big = receipt_attachment(file_size=MAX_RECEIPT_BYTES + 1)

    reply = await paid_bot.say("", attachments=(big,))

    assert reply == texts.RECEIPT_UNREADABLE
    assert paid_bot.register_receipt.registered == []
    assert _handoffs(paid_bot) == []


async def test_an_attachment_that_is_not_an_image_or_pdf_asks_to_resend(
    paid_bot: BotHarness,
) -> None:
    audio = receipt_attachment(file_type="audio", content_type="audio/ogg")

    reply = await paid_bot.say("", attachments=(audio,))

    assert reply == texts.RECEIPT_UNREADABLE
    assert paid_bot.register_receipt.registered == []
    assert _handoffs(paid_bot) == []


# --- Fallas ------------------------------------------------------------------------------------


@pytest.mark.parametrize("error", [MessagingUnavailableError("caído"), None])
async def test_an_unavailable_download_still_hands_off_without_a_payment(
    paid_bot: BotHarness, error: Exception | None
) -> None:
    if error is not None:
        paid_bot.messaging.download_error = error
    # Con ``None`` el adjunto no existe: ``ResourceNotFoundError``.

    reply = await paid_bot.say("", attachments=(receipt_attachment(),))

    assert reply == texts.RECEIPT_REGISTERED
    assert paid_bot.register_receipt.registered == []
    assert paid_bot.storage.stored == {}
    assert _link(paid_bot).handoff_reason is HandoffReason.PAYMENT_RECEIPT
    assert len(_handoffs(paid_bot)) == 1


async def test_an_active_advance_is_not_duplicated_but_still_hands_off(
    paid_bot: BotHarness,
) -> None:
    paid_bot.register_receipt.error = ResourceInUseError("ya hay un adelanto")

    reply = await _send_receipt(paid_bot)

    assert reply == texts.RECEIPT_REGISTERED
    assert paid_bot.register_receipt.registered == []
    assert paid_bot.storage.deleted == ["evidence/receipt-1.png"]
    assert _link(paid_bot).handoff_reason is HandoffReason.PAYMENT_RECEIPT


async def test_a_database_failure_deletes_the_stored_file_and_follows_the_error_path(
    paid_bot: BotHarness,
) -> None:
    paid_bot.register_receipt.error = RuntimeError("base de datos caída")

    reply = await _send_receipt(paid_bot)

    assert reply == texts.HANDOFF_ERROR
    assert paid_bot.storage.deleted == ["evidence/receipt-1.png"]
    assert paid_bot.storage.stored == {}
    assert _link(paid_bot).handoff_reason is HandoffReason.BOT_ERROR


async def test_a_failed_cleanup_does_not_hide_the_original_error(paid_bot: BotHarness) -> None:
    async def broken_delete(evidence_path: str) -> None:
        raise OSError("disco")

    paid_bot.storage.delete = broken_delete  # type: ignore[method-assign]
    paid_bot.register_receipt.error = RuntimeError("base de datos caída")

    reply = await _send_receipt(paid_bot)

    assert reply == texts.HANDOFF_ERROR
    assert _link(paid_bot).handoff_reason is HandoffReason.BOT_ERROR


# --- Piezas --------------------------------------------------------------------------------------


def test_the_new_reason_maps_to_payment_receipt() -> None:
    assert map_reason("payment_receipt") is HandoffReason.PAYMENT_RECEIPT
    assert map_reason("desconocido") is HandoffReason.BOT_ERROR


def test_the_receipt_summary_extends_or_replaces_the_session_summary() -> None:
    assert (
        receipt_summary("Cotización abc: Lima")
        == "Cotización abc: Lima. Comprobante de pago recibido"
    )
    assert receipt_summary(None) == "Comprobante de pago recibido"


@pytest.mark.parametrize(
    ("attachment", "accepted"),
    [
        (MessageAttachment(1, "image", "image/jpeg"), True),
        (MessageAttachment(1, "file", "application/pdf"), True),
        (MessageAttachment(1, "file", None, extension="pdf"), True),
        (MessageAttachment(1, "image", None), True),
        (MessageAttachment(1, "audio", "audio/ogg"), False),
        (MessageAttachment(1, "file", "application/zip"), False),
    ],
)
def test_only_images_and_pdfs_are_candidates(attachment: MessageAttachment, accepted: bool) -> None:
    assert (first_receipt_attachment([attachment]) is not None) is accepted
