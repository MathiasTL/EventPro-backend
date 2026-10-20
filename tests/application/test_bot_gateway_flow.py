"""Del webhook al bot: ``ProcessGatewayEvent`` entrega los mensajes de clientes a quien responde."""

import copy
import json
from datetime import UTC, datetime
from typing import Any

from app.application.dtos.gateway_event_dto import GatewayEventOutcome, IncomingClientMessage
from app.application.use_cases.messaging.process_gateway_event import ProcessGatewayEvent
from app.infrastructure.adapters.secondary.external_services.chatwoot.chatwoot_event_gateway import (  # noqa: E501
    ChatwootEventGateway,
)
from tests.application.bot_support import PHONE, BotHarness
from tests.application.outbox_support import InMemoryOutboxStore
from tests.chatwoot_fixture_support import load_fixture

RECEIVED_AT = datetime(2026, 10, 9, 15, 0, tzinfo=UTC)


def _raw(*, status: str = "pending", message_id: int = 5, content: str = "Hola") -> bytes:
    body: dict[str, Any] = copy.deepcopy(load_fixture("message_created_incoming")["body"])
    body["id"] = message_id
    body["content"] = content
    body["conversation"]["status"] = status
    return json.dumps(body).encode()


def _process_use_case(bot: BotHarness) -> ProcessGatewayEvent:
    return ProcessGatewayEvent(
        transaction=InMemoryOutboxStore().transaction,
        gateway=ChatwootEventGateway(None),
        incoming_handler=bot.use_case,
    )


class _Recorder:
    def __init__(self, outcome: GatewayEventOutcome) -> None:
        self.outcome = outcome
        self.messages: list[IncomingClientMessage] = []

    async def execute(self, message: IncomingClientMessage) -> GatewayEventOutcome:
        self.messages.append(message)
        return self.outcome


async def test_a_pending_client_message_reaches_the_handler_and_its_outcome_is_returned() -> None:
    recorder = _Recorder(GatewayEventOutcome.APPLIED)
    use_case = ProcessGatewayEvent(
        transaction=InMemoryOutboxStore().transaction,
        gateway=ChatwootEventGateway(None),
        incoming_handler=recorder,
    )

    outcome = await use_case.execute(raw_body=_raw(), received_at=RECEIVED_AT)

    assert outcome is GatewayEventOutcome.APPLIED
    (message,) = recorder.messages
    assert (message.external_message_id, message.content, message.sender_phone) == (
        "5",
        "Hola",
        PHONE,
    )


async def test_without_a_handler_a_client_message_is_only_logged() -> None:
    use_case = ProcessGatewayEvent(
        transaction=InMemoryOutboxStore().transaction, gateway=ChatwootEventGateway(None)
    )

    outcome = await use_case.execute(raw_body=_raw(), received_at=RECEIVED_AT)

    assert outcome is GatewayEventOutcome.UNHANDLED


async def test_the_bot_answers_a_real_webhook_body_with_the_greeting() -> None:
    bot = BotHarness()

    outcome = await _process_use_case(bot).execute(raw_body=_raw(), received_at=RECEIVED_AT)

    assert outcome is GatewayEventOutcome.APPLIED
    (greeting,) = bot.sent
    assert greeting.startswith("Hola, te damos la bienvenida a EventPro")
    (message,) = bot.outbox.messages.values()
    assert message.recipient == PHONE


async def test_a_conversation_attended_by_a_person_gets_no_answer() -> None:
    bot = BotHarness()

    outcome = await _process_use_case(bot).execute(
        raw_body=_raw(status="open"), received_at=RECEIVED_AT
    )

    assert outcome is GatewayEventOutcome.IGNORED
    assert bot.sent == []


async def test_redelivering_the_same_webhook_does_not_answer_twice() -> None:
    bot = BotHarness()
    use_case = _process_use_case(bot)
    await use_case.execute(raw_body=_raw(message_id=5), received_at=RECEIVED_AT)
    await use_case.execute(raw_body=_raw(message_id=6, content="3"), received_at=RECEIVED_AT)
    sent = list(bot.sent)

    # Un reintento del trabajo de arq o un reenvío de Chatwoot repite el mensaje 6.
    outcome = await use_case.execute(
        raw_body=_raw(message_id=6, content="3"), received_at=RECEIVED_AT
    )

    assert outcome is GatewayEventOutcome.IGNORED
    assert bot.sent == sent


async def test_an_outgoing_message_of_the_bot_itself_is_never_answered() -> None:
    bot = BotHarness()
    body = copy.deepcopy(load_fixture("message_created_outgoing")["body"])

    outcome = await _process_use_case(bot).execute(
        raw_body=json.dumps(body).encode(), received_at=RECEIVED_AT
    )

    assert outcome is GatewayEventOutcome.UNHANDLED
    assert bot.sent == []
