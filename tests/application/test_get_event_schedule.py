from collections.abc import Sequence
from datetime import date, time
from uuid import UUID, uuid4

import pytest

from app.application.dtos.event_schedule_dto import (
    CrewScheduleDTO,
    EventScheduleFilters,
    QuoteScheduleDTO,
    ScheduleActor,
)
from app.application.use_cases.event.get_event_schedule import (
    GetEventScheduleUseCase,
    ScheduleAssignmentRequiredError,
)
from app.domain.entities.event import Event
from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.event_status import EventStatus
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.secondary.external_services.fake_schedule_adapters import (
    FakeCrewScheduleReadAdapter,
    FakeQuoteScheduleReadAdapter,
)
from tests.event_support import make_event


class FakeEventRepository:
    def __init__(self, events: Sequence[Event]) -> None:
        self.events = events
        self.calls: list[tuple[EventScheduleFilters, frozenset[UUID] | None]] = []

    async def list_for_schedule(
        self, filters: EventScheduleFilters, *, event_ids: frozenset[UUID] | None = None
    ) -> Sequence[Event]:
        self.calls.append((filters, event_ids))
        return sorted(
            (
                event
                for event in self.events
                if (filters.from_date is None or event.event_date >= filters.from_date)
                and (filters.to_date is None or event.event_date <= filters.to_date)
                and (filters.status is None or event.status == filters.status)
                and (event_ids is None or event.id in event_ids)
            ),
            key=lambda event: (event.event_date, event.start_time, event.id),
        )


def actor(role: Role = Role.ENCARGADO) -> ScheduleActor:
    return ScheduleActor(user_id=uuid4(), role=role)


@pytest.mark.parametrize(
    "filters,expected",
    [
        (EventScheduleFilters(), [0, 1, 2, 3]),
        (EventScheduleFilters(from_date=date(2026, 10, 15)), [1, 2, 3]),
        (EventScheduleFilters(to_date=date(2026, 10, 15)), [0, 1, 2]),
        (EventScheduleFilters(status=EventStatus.SCHEDULED), [0, 1, 3]),
        (
            EventScheduleFilters(
                from_date=date(2026, 10, 15),
                to_date=date(2026, 10, 15),
                status=EventStatus.SCHEDULED,
            ),
            [1],
        ),
        (EventScheduleFilters(from_date=date(2026, 11, 1)), []),
    ],
)
async def test_schedule_filters_are_combined_and_inclusive(
    filters: EventScheduleFilters, expected: list[int]
) -> None:
    events = [
        make_event(event_date=date(2026, 10, 14), status=EventStatus.SCHEDULED),
        make_event(status=EventStatus.SCHEDULED, start_time=time(10)),
        make_event(status=EventStatus.CANCELLED),
        make_event(event_date=date(2026, 10, 16), status=EventStatus.SCHEDULED),
    ]
    repo = FakeEventRepository(list(reversed(events)))
    use_case = GetEventScheduleUseCase(
        repo, FakeQuoteScheduleReadAdapter(), FakeCrewScheduleReadAdapter()
    )
    result = await use_case.execute(filters, actor())
    assert [item.event_id for item in result] == [events[index].id for index in expected]
    assert repo.calls == [(filters, None)]


async def test_invalid_range_does_not_query_repository() -> None:
    repo = FakeEventRepository([])
    use_case = GetEventScheduleUseCase(
        repo, FakeQuoteScheduleReadAdapter(), FakeCrewScheduleReadAdapter()
    )
    with pytest.raises(ValidationError):
        await use_case.execute(
            EventScheduleFilters(from_date=date(2026, 10, 16), to_date=date(2026, 10, 15)), actor()
        )
    assert repo.calls == []


async def test_enrichment_and_observations_are_preserved() -> None:
    event = make_event(client_observations="  Gorila al min 45.\nSin reggaetón. ")
    crew = CrewScheduleDTO(crew_id=uuid4(), leader_name="Luis Torres")
    quotes = FakeQuoteScheduleReadAdapter(
        {
            event.quote_id: QuoteScheduleDTO(
                client_name="Carlos Rodríguez", package_name="Hora Loca Medium", theme_name="Selva"
            )
        }
    )
    crews = FakeCrewScheduleReadAdapter(crews_by_event={event.id: (crew,)})
    result = await GetEventScheduleUseCase(FakeEventRepository([event]), quotes, crews).execute(
        EventScheduleFilters(), actor()
    )
    item = result[0]
    assert (item.client_name, item.package_name, item.theme_name) == (
        "Carlos Rodríguez",
        "Hora Loca Medium",
        "Selva",
    )
    assert item.crews == (crew,)
    assert item.client_observations == event.client_observations
    assert item.pending_balance_to_collect == event.pending_balance_to_collect.amount


@pytest.mark.parametrize("role", [Role.ENCARGADO, Role.SUPERADMIN])
async def test_administrative_roles_get_placeholder_details(role: Role) -> None:
    repo = FakeEventRepository([make_event()])
    result = await GetEventScheduleUseCase(
        repo, FakeQuoteScheduleReadAdapter(), FakeCrewScheduleReadAdapter()
    ).execute(EventScheduleFilters(), actor(role))
    assert result[0].client_name == "Cliente pendiente de integración"
    assert result[0].package_name == "Paquete pendiente de integración"
    assert result[0].theme_name == "Temática pendiente de integración"
    assert result[0].crews == ()
    assert repo.calls[0][1] is None


async def test_operator_is_restricted_to_own_assignments() -> None:
    own, other = make_event(), make_event()
    operator = actor(Role.OPERADOR)
    repo = FakeEventRepository([own, other])
    crews = FakeCrewScheduleReadAdapter(
        assigned_events_by_user={operator.user_id: frozenset({own.id})}
    )
    result = await GetEventScheduleUseCase(repo, FakeQuoteScheduleReadAdapter(), crews).execute(
        EventScheduleFilters(), operator
    )
    assert [item.event_id for item in result] == [own.id]
    assert repo.calls[0][1] == frozenset({own.id})


async def test_operator_without_assignments_is_denied_before_query() -> None:
    repo = FakeEventRepository([make_event()])
    use_case = GetEventScheduleUseCase(
        repo, FakeQuoteScheduleReadAdapter(), FakeCrewScheduleReadAdapter()
    )
    with pytest.raises(ScheduleAssignmentRequiredError, match="asignación activa"):
        await use_case.execute(EventScheduleFilters(), actor(Role.OPERADOR))
    assert repo.calls == []
