from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.financial_reporting import FinancialReportingService
from app.domain.value_objects.event_status import EventStatus
from app.domain.value_objects.financial_reporting import EventDirectCosts
from app.domain.value_objects.money import Money
from app.infrastructure.adapters.secondary.persistence.repositories import (
    sqlalchemy_event_repository,
)
from tests.event_support import make_event


async def test_log_failure_does_not_roll_back_a_committed_settlement(monkeypatch):
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = Mock()
    event = make_event(status=EventStatus.SETTLED)
    session.execute.return_value.scalar_one_or_none.return_value = event.id
    snapshot = FinancialReportingService.snapshot(
        event,
        EventDirectCosts(uuid4(), Money.zero(), (), Money.zero()),
        Money.zero(),
        datetime(2026, 10, 15, tzinfo=UTC),
    )
    logger = Mock()

    def fail_log(*args, **kwargs):
        session.commit.assert_awaited_once()
        raise RuntimeError("logger unavailable")

    logger.info.side_effect = fail_log
    monkeypatch.setattr(sqlalchemy_event_repository, "get_logger", Mock(return_value=logger))
    repository = sqlalchemy_event_repository.SqlAlchemyEventRepository(session)

    with pytest.raises(RuntimeError, match="logger unavailable"):
        await repository.save_settlement(event, snapshot)

    session.rollback.assert_not_awaited()
