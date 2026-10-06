from decimal import Decimal
from uuid import uuid4

import pytest

from app.application.dtos.event_schedule_dto import ScheduleActor
from app.application.use_cases.event.start_event import EventAccessDeniedError, StartEventUseCase
from app.domain.exceptions.event_exceptions import BalancePendingError, InvalidEventStateError
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError
from app.domain.value_objects.event_status import EventStatus
from app.domain.value_objects.money import Money
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.secondary.external_services.fake_schedule_adapters import (
    FakeCrewScheduleReadAdapter,
)
from tests.event_support import make_event
from tests.start_event_support import (
    STARTED_AT,
    FakeStartEventRepository,
    FixedClock,
    RecordingPayments,
)


@pytest.mark.parametrize("role", [Role.ENCARGADO, Role.SUPERADMIN, Role.OPERADOR])
@pytest.mark.parametrize("status", [EventStatus.SCHEDULED, EventStatus.AWAITING_BALANCE])
async def test_start_saves_verified_total_and_server_instant(
    role: Role, status: EventStatus
) -> None:
    event = make_event(status=status, pre_show_balance_paid=Money(Decimal("100")))
    actor = ScheduleActor(uuid4(), role)
    repo = FakeStartEventRepository((event,))
    payments = RecordingPayments({event.id: Money(Decimal("980.50"))})
    clock = FixedClock()
    crews = FakeCrewScheduleReadAdapter(
        assigned_events_by_user={actor.user_id: frozenset({event.id})}
    )
    result = await StartEventUseCase(repo, payments, crews, clock).execute(event.id, actor)
    assert result.event_id == event.id
    assert result.status is EventStatus.IN_PROGRESS
    assert result.actual_start_time == STARTED_AT
    assert payments.calls == [event.id]
    assert clock.calls == 1
    assert len(repo.saves) == 1
    assert repo.events[event.id].pre_show_balance_paid == Money(Decimal("980.50"))


async def test_paid_cache_cannot_replace_verified_payments() -> None:
    event = make_event(status=EventStatus.SCHEDULED, pre_show_balance_paid=Money(Decimal("980.50")))
    repo, payments, clock = FakeStartEventRepository((event,)), RecordingPayments(), FixedClock()
    with pytest.raises(BalancePendingError):
        await StartEventUseCase(repo, payments, FakeCrewScheduleReadAdapter(), clock).execute(
            event.id, ScheduleActor(uuid4(), Role.ENCARGADO)
        )
    assert repo.saves == []
    assert repo.events[event.id] == event


@pytest.mark.parametrize(
    "status",
    [
        EventStatus.AWAITING_SIGNATURE,
        EventStatus.IN_PROGRESS,
        EventStatus.EXTENDED,
        EventStatus.SETTLED,
        EventStatus.CANCELLED,
    ],
)
async def test_invalid_state_does_not_query_payments_or_save(status: EventStatus) -> None:
    event = make_event(status=status)
    repo, payments, clock = FakeStartEventRepository((event,)), RecordingPayments(), FixedClock()
    with pytest.raises(InvalidEventStateError):
        await StartEventUseCase(repo, payments, FakeCrewScheduleReadAdapter(), clock).execute(
            event.id, ScheduleActor(uuid4(), Role.ENCARGADO)
        )
    assert payments.calls == repo.saves == []
    assert clock.calls == 0


async def test_operator_outside_scope_is_rejected_before_load() -> None:
    event = make_event(status=EventStatus.SCHEDULED)
    repo, payments = FakeStartEventRepository((event,)), RecordingPayments()
    with pytest.raises(EventAccessDeniedError):
        await StartEventUseCase(
            repo, payments, FakeCrewScheduleReadAdapter(), FixedClock()
        ).execute(event.id, ScheduleActor(uuid4(), Role.OPERADOR))
    assert repo.loads == payments.calls == repo.saves == []


@pytest.mark.parametrize("role", [Role.ENCARGADO, Role.OPERADOR])
async def test_missing_authorized_event_is_not_found(role: Role) -> None:
    event_id, actor = uuid4(), ScheduleActor(uuid4(), role)
    repo, payments = FakeStartEventRepository(), RecordingPayments()
    crews = FakeCrewScheduleReadAdapter(
        assigned_events_by_user={actor.user_id: frozenset({event_id})}
    )
    with pytest.raises(ResourceNotFoundError):
        await StartEventUseCase(repo, payments, crews, FixedClock()).execute(event_id, actor)
    assert repo.loads == [event_id]
    assert payments.calls == repo.saves == []


async def test_save_failure_does_not_report_success() -> None:
    event = make_event(status=EventStatus.SCHEDULED)
    repo = FakeStartEventRepository((event,))
    repo.fail_save = True
    payments = RecordingPayments({event.id: Money(Decimal("980.50"))})
    with pytest.raises(RuntimeError, match="persistir"):
        await StartEventUseCase(
            repo, payments, FakeCrewScheduleReadAdapter(), FixedClock()
        ).execute(event.id, ScheduleActor(uuid4(), Role.SUPERADMIN))
    assert repo.saves == []
    assert repo.events[event.id] == event


async def test_repeated_start_does_not_reverify_payment() -> None:
    event = make_event(status=EventStatus.SCHEDULED)
    repo, payments = (
        FakeStartEventRepository((event,)),
        RecordingPayments({event.id: Money(Decimal("980.50"))}),
    )
    use_case = StartEventUseCase(repo, payments, FakeCrewScheduleReadAdapter(), FixedClock())
    actor = ScheduleActor(uuid4(), Role.ENCARGADO)
    await use_case.execute(event.id, actor)
    with pytest.raises(InvalidEventStateError):
        await use_case.execute(event.id, actor)
    assert payments.calls == [event.id]
    assert len(repo.saves) == 1
