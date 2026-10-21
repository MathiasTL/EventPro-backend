"""Unidad de trabajo de los eventos de la bandeja sobre PostgreSQL 16 real (spec 09, 6.1)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.dtos.gateway_event_dto import (
    ConversationSnapshot,
    GatewayEvent,
    GatewayEventOutcome,
    IncomingClientMessage,
    MessageDetails,
    OutgoingMessageEcho,
)
from app.application.dtos.messaging_dto import ConversationLifecycle, ConversationStatus
from app.application.use_cases.messaging.process_gateway_event import ProcessGatewayEvent
from app.domain.entities.client import Client
from app.domain.value_objects.phone_number import PhoneNumber
from app.infrastructure.adapters.secondary.events.in_memory_conversation_event_publisher import (
    InMemoryConversationEventPublisher,
)
from app.infrastructure.adapters.secondary.persistence.database import build_engine
from app.infrastructure.adapters.secondary.persistence.repositories import (
    sqlalchemy_client_repository,
    sqlalchemy_conversation_link_repository,
    sqlalchemy_outbox_repository,
)
from app.infrastructure.adapters.secondary.persistence.sqlalchemy_inbox_event_unit_of_work import (
    SqlAlchemyInboxEventUnitOfWork,
)
from tests.application.test_inbox_gateway_events import RAW_BODY, RECEIVED_AT, _Bot, _Gateway
from tests.domain.outbox_support import NOW, make_message

from ._support import insert_user, run_migrations

pytestmark = pytest.mark.integration

CONVERSATION = 4202
PHONE = PhoneNumber("+51999777666")


@pytest.fixture(scope="module")
def migrated_url(database_url: str) -> str:
    run_migrations(database_url)
    return database_url


@pytest.fixture
async def engine(migrated_url: str) -> AsyncIterator[AsyncEngine]:
    engine = build_engine(migrated_url)
    async with engine.begin() as connection:
        await connection.execute(text("DELETE FROM conversation_links"))
        await connection.execute(text("DELETE FROM outbox_messages"))
        await connection.execute(text("DELETE FROM clients WHERE phone = :p"), {"p": PHONE.value})
    yield engine
    await engine.dispose()


@pytest.fixture
def factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def _use_case(
    factory: async_sessionmaker[AsyncSession], event: GatewayEvent
) -> tuple[ProcessGatewayEvent, InMemoryConversationEventPublisher, _Bot]:
    publisher = InMemoryConversationEventPublisher()
    bot = _Bot()
    use_case = ProcessGatewayEvent(
        transaction=sqlalchemy_outbox_repository.SqlAlchemyOutboxTransaction(factory),
        gateway=_Gateway(event),
        incoming_handler=bot,
        inbox=SqlAlchemyInboxEventUnitOfWork(factory),
        publisher=publisher,
    )
    return use_case, publisher, bot


def _snapshot() -> ConversationSnapshot:
    return ConversationSnapshot(
        lifecycle=ConversationLifecycle.OPEN, unread_count=1, can_reply=True, contact_phone=PHONE
    )


async def test_find_by_message_reference_matches_the_current_and_the_retried_id(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    sent = make_message()
    sent.mark_sent(external_message_id="cw-1", conversation_id=CONVERSATION, now=NOW)
    retried = make_message()
    retried.retried_external_message_id = "cw-2"
    async with factory() as session, session.begin():
        repository = sqlalchemy_outbox_repository.SqlAlchemyOutboxRepository(session)
        await repository.add(sent)
        await repository.add(retried)

    async with factory() as session:
        repository = sqlalchemy_outbox_repository.SqlAlchemyOutboxRepository(session)
        found_current = await repository.find_by_message_reference("cw-1")
        found_retried = await repository.find_by_message_reference("cw-2")
        missing = await repository.find_by_message_reference("cw-3")

    assert found_current is not None and found_current.id == sent.id
    assert found_retried is not None and found_retried.id == retried.id
    assert missing is None


async def test_an_incoming_message_persists_the_link_with_the_registered_client(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    client = Client(phone=PHONE, full_name="Carlos Ramírez")
    async with factory() as session, session.begin():
        await sqlalchemy_client_repository.SqlAlchemyClientRepository(session).get_or_create(
            PHONE.value, client.full_name
        )
    message = IncomingClientMessage(
        external_message_id="900",
        conversation_id=CONVERSATION,
        conversation_status=ConversationStatus.HUMAN,
        sender_phone=PHONE,
        content="Hola",
        snapshot=_snapshot(),
        details=MessageDetails(sent_at=NOW),
    )
    use_case, publisher, bot = _use_case(factory, message)

    outcome = await use_case.execute(raw_body=RAW_BODY, received_at=RECEIVED_AT)

    assert outcome is GatewayEventOutcome.APPLIED
    assert bot.messages == []
    assert [e.event.value for e in publisher.events] == ["message.created", "conversation.updated"]
    async with factory() as session:
        link = await sqlalchemy_conversation_link_repository.SqlAlchemyConversationLinkRepository(
            session
        ).get(CONVERSATION)
        stored = await sqlalchemy_client_repository.SqlAlchemyClientRepository(
            session
        ).get_by_phone(PHONE.value)
    assert link is not None and stored is not None
    assert (link.client_id, link.last_client_message_at) == (stored.id, NOW)


async def test_an_echo_resolves_the_agent_from_the_real_outbox(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession]
) -> None:
    author = await insert_user(engine, "ENCARGADO")
    row = make_message(author_user_id=author)
    row.mark_sent(external_message_id="901", conversation_id=CONVERSATION, now=NOW)
    async with factory() as session, session.begin():
        await sqlalchemy_outbox_repository.SqlAlchemyOutboxRepository(session).add(row)
    echo = OutgoingMessageEcho(
        external_message_id="901",
        conversation_id=CONVERSATION,
        content="Claro",
        snapshot=_snapshot(),
    )
    use_case, publisher, _ = _use_case(factory, echo)

    outcome = await use_case.execute(raw_body=RAW_BODY, received_at=RECEIVED_AT)

    assert outcome is GatewayEventOutcome.APPLIED
    message = publisher.events[0].data["message"]
    assert (message["author_type"], message["outbox_id"]) == ("AGENT", str(row.id))
