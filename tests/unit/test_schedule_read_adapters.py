from unittest.mock import AsyncMock

from app.infrastructure.adapters.secondary.persistence.repositories.sqlalchemy_schedule_read_adapters import (  # noqa: E501
    SqlAlchemyCrewScheduleReadAdapter,
    SqlAlchemyQuoteScheduleReadAdapter,
)


async def test_empty_schedule_detail_inputs_skip_database():
    session = AsyncMock()
    assert await SqlAlchemyQuoteScheduleReadAdapter(session).get_details(frozenset()) == {}
    assert await SqlAlchemyCrewScheduleReadAdapter(session).get_crews(frozenset()) == {}
    session.execute.assert_not_awaited()
