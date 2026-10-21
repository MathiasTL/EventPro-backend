"""RF-22 / US-20: override del intervalo de tránsito contra PostgreSQL 16 real."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.dtos.override_dto import OverrideTransitIntervalInput
from app.application.services.audit_service import AuditService
from app.application.use_cases.crew.override_transit_interval import (
    OverrideCrewTransitIntervalUseCase,
)
from app.domain.entities.audit_log import AuditLog
from app.domain.exceptions.event_exceptions import InvalidEventStateError
from app.domain.value_objects.event_status import EventStatus
from app.infrastructure.adapters.secondary.persistence.database import build_engine
from app.infrastructure.adapters.secondary.persistence.mappers.event_mapper import event_to_model
from app.infrastructure.adapters.secondary.persistence.repositories.sqlalchemy_crew_assignment_repository import (  # noqa: E501
    SqlAlchemyCrewAssignmentRepository,
)
from app.infrastructure.adapters.secondary.persistence.repositories.sqlalchemy_event_repository import (  # noqa: E501
    SqlAlchemyEventRepository,
)
from tests.event_support import make_event
from tests.integration._support import insert_quotes, run_migrations

pytestmark = pytest.mark.integration


class _NoopAuditPort:
    async def record(self, entry: AuditLog) -> None:
        return None


@pytest.fixture(scope="module")
def migrated_url(database_url: str) -> str:
    run_migrations(database_url)
    return database_url


@pytest.fixture
async def engine(migrated_url: str):
    engine = build_engine(migrated_url)
    yield engine
    await engine.dispose()


@pytest.fixture
def factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _seed_assignment(
    engine: AsyncEngine,
    factory: async_sessionmaker[AsyncSession],
    *,
    event_status: EventStatus,
    transit_interval_minutes: int | None = 45,
) -> tuple[UUID, UUID]:
    """Crea un evento con su cotización y una asignación de elenco; devuelve sus ids."""

    event = make_event(status=event_status)
    await insert_quotes(engine, [event.quote_id])
    async with factory() as session:
        session.add(event_to_model(event))
        await session.commit()
    async with engine.begin() as connection:
        crew_id = await connection.scalar(
            text(
                "INSERT INTO crews (leader_name, phone, service_category) "
                "VALUES ('Elenco de prueba', '51900000000', 'SHOW') RETURNING id"
            )
        )
        assignment_id = await connection.scalar(
            text(
                "INSERT INTO crew_assignments (event_id, crew_id, transit_interval_minutes) "
                "VALUES (:event, :crew, :interval) RETURNING id"
            ),
            {"event": event.id, "crew": crew_id, "interval": transit_interval_minutes},
        )
    return event.id, assignment_id


async def test_override_persists_interval_and_marks_overridden(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession]
) -> None:
    _event_id, assignment_id = await _seed_assignment(
        engine, factory, event_status=EventStatus.SCHEDULED
    )

    async with factory() as session:
        use_case = OverrideCrewTransitIntervalUseCase(
            SqlAlchemyCrewAssignmentRepository(session),
            SqlAlchemyEventRepository(session),
            AuditService(_NoopAuditPort()),
        )
        result = await use_case.execute(
            OverrideTransitIntervalInput(
                assignment_id=assignment_id,
                transit_interval_minutes=35,
                reason="Ruta alterna sin tráfico confirmada por el elenco",
                decided_by_user_id=uuid4(),
            )
        )
        await session.commit()

    assert result.transit_interval_minutes == 35
    assert result.transit_interval_overridden is True

    async with engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    "SELECT transit_interval_minutes, transit_interval_overridden "
                    "FROM crew_assignments WHERE id = :id"
                ),
                {"id": assignment_id},
            )
        ).one()
    assert row.transit_interval_minutes == 35
    assert row.transit_interval_overridden is True


async def test_override_on_started_event_raises_without_persisting(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession]
) -> None:
    _event_id, assignment_id = await _seed_assignment(
        engine, factory, event_status=EventStatus.IN_PROGRESS
    )

    async with factory() as session:
        use_case = OverrideCrewTransitIntervalUseCase(
            SqlAlchemyCrewAssignmentRepository(session),
            SqlAlchemyEventRepository(session),
            AuditService(_NoopAuditPort()),
        )
        with pytest.raises(InvalidEventStateError):
            await use_case.execute(
                OverrideTransitIntervalInput(
                    assignment_id=assignment_id,
                    transit_interval_minutes=35,
                    reason="Ruta alterna sin tráfico confirmada por el elenco",
                    decided_by_user_id=uuid4(),
                )
            )
        await session.rollback()

    async with engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    "SELECT transit_interval_minutes, transit_interval_overridden "
                    "FROM crew_assignments WHERE id = :id"
                ),
                {"id": assignment_id},
            )
        ).one()
    assert row.transit_interval_minutes == 45
    assert row.transit_interval_overridden is False
