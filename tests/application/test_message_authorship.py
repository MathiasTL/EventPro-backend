"""Autoría de los mensajes de la bandeja (spec 09, 4.3, D3)."""

from uuid import uuid4

import pytest

from app.application.dtos.messaging_dto import AuthorType, MessageDirection, MessageSender
from app.application.use_cases.messaging.message_authorship import resolve_author_type
from tests.domain.outbox_support import make_message

OUT = MessageDirection.OUTGOING


def test_an_incoming_message_is_always_from_the_client() -> None:
    author = resolve_author_type(
        direction=MessageDirection.INCOMING, outbox=None, sender=MessageSender.CONTACT
    )

    assert author is AuthorType.CLIENT


def test_an_activity_notice_has_no_author_and_is_never_the_bot() -> None:
    author = resolve_author_type(direction=MessageDirection.ACTIVITY, outbox=None, sender=None)

    assert author is None


def test_an_outbox_row_with_an_author_is_an_agent_even_if_chatwoot_says_bot() -> None:
    row = make_message(author_user_id=uuid4())

    assert (
        resolve_author_type(direction=OUT, outbox=row, sender=MessageSender.AGENT_BOT)
        is AuthorType.AGENT
    )


def test_an_outbox_row_without_an_author_is_the_bot_even_if_chatwoot_says_user() -> None:
    row = make_message()

    assert (
        resolve_author_type(direction=OUT, outbox=row, sender=MessageSender.USER) is AuthorType.BOT
    )


@pytest.mark.parametrize(
    ("sender", "expected"),
    [
        (MessageSender.USER, AuthorType.AGENT),
        (MessageSender.AGENT_BOT, AuthorType.BOT),
        (MessageSender.CONTACT, AuthorType.BOT),
        (None, AuthorType.BOT),
    ],
)
def test_without_an_outbox_row_the_chatwoot_sender_decides(
    sender: MessageSender | None, expected: AuthorType
) -> None:
    assert resolve_author_type(direction=OUT, outbox=None, sender=sender) is expected
