"""SqlAlchemyBotUnitOfWork: una sesión por turno, confirmada o revertida con el bloque."""

from types import TracebackType
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.ports.output.bot_unit_of_work_port import BotTransaction
from app.infrastructure.adapters.secondary.persistence.sqlalchemy_bot_unit_of_work import (
    SqlAlchemyBotUnitOfWork,
)


class _Begin:
    def __init__(self, session: "_Session") -> None:
        self._session = session

    async def __aenter__(self) -> None:
        self._session.events.append("begin")

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._session.events.append("rollback" if exc_type else "commit")


class _Session:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def begin(self) -> _Begin:
        return _Begin(self)

    async def __aenter__(self) -> "_Session":
        self.events.append("open")
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        self.events.append("close")


def _unit_of_work() -> tuple[SqlAlchemyBotUnitOfWork, list[str], list[Any]]:
    events: list[str] = []
    sessions: list[Any] = []
    transaction = cast("BotTransaction", object())

    def build(session: AsyncSession) -> BotTransaction:
        sessions.append(session)
        return transaction

    def factory() -> _Session:
        return _Session(events)

    unit = SqlAlchemyBotUnitOfWork(cast("async_sessionmaker[AsyncSession]", factory), build)
    return unit, events, sessions


async def test_the_block_runs_inside_one_transaction_that_commits() -> None:
    unit, events, sessions = _unit_of_work()

    async with unit() as transaction:
        events.append("work")
        assert transaction is not None

    assert events == ["open", "begin", "work", "commit", "close"]
    assert len(sessions) == 1


async def test_a_failing_block_rolls_back_and_propagates_the_error() -> None:
    unit, events, _ = _unit_of_work()

    with pytest.raises(RuntimeError, match="falla"):
        async with unit():
            raise RuntimeError("falla")

    assert events == ["open", "begin", "rollback", "close"]


async def test_each_turn_builds_its_use_cases_on_its_own_session() -> None:
    unit, _, sessions = _unit_of_work()

    async with unit():
        pass
    async with unit():
        pass

    assert len(sessions) == 2
    assert sessions[0] is not sessions[1]
