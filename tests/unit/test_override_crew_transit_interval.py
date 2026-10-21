"""Pruebas unitarias de OverrideCrewTransitIntervalUseCase (RF-22, US-20)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.dtos.crew_assignment_dto import CrewAssignmentDTO
from app.application.dtos.override_dto import OverrideTransitIntervalInput
from app.application.services.audit_service import AuditService
from app.application.use_cases.crew.override_transit_interval import (
    OverrideCrewTransitIntervalUseCase,
)
from app.domain.exceptions.event_exceptions import InvalidEventStateError
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError
from app.domain.value_objects.event_status import EventStatus
from tests.event_support import make_event

USER_ID = uuid4()


def _assignment(
    event_id, *, minutes: int | None = 45, overridden: bool = False
) -> CrewAssignmentDTO:
    return CrewAssignmentDTO(
        id=uuid4(),
        event_id=event_id,
        crew_id=uuid4(),
        transit_interval_minutes=minutes,
        transit_interval_overridden=overridden,
    )


def _use_case(
    assignment: CrewAssignmentDTO | None, event
) -> tuple[OverrideCrewTransitIntervalUseCase, AsyncMock, AsyncMock, AsyncMock]:
    assignments = AsyncMock()
    assignments.get_by_id.return_value = assignment
    events = AsyncMock()
    events.get_by_id_for_update.return_value = event
    audit_port = AsyncMock()
    use_case = OverrideCrewTransitIntervalUseCase(assignments, events, AuditService(audit_port))
    return use_case, assignments, events, audit_port


def _input(assignment_id, *, minutes: int = 35, reason: str = "Ruta alterna confirmada"):
    return OverrideTransitIntervalInput(
        assignment_id=assignment_id,
        transit_interval_minutes=minutes,
        reason=reason,
        decided_by_user_id=USER_ID,
    )


def test_override_updates_interval_and_marks_overridden() -> None:
    event = make_event(status=EventStatus.SCHEDULED)
    assignment = _assignment(event.id)
    use_case, assignments, events, audit_port = _use_case(assignment, event)
    updated = CrewAssignmentDTO(
        id=assignment.id,
        event_id=event.id,
        crew_id=assignment.crew_id,
        transit_interval_minutes=35,
        transit_interval_overridden=True,
    )
    assignments.override_transit_interval.return_value = updated

    result = asyncio.run(use_case.execute(_input(assignment.id)))

    events.get_by_id_for_update.assert_awaited_once_with(event.id)
    assignments.override_transit_interval.assert_awaited_once_with(
        assignment.id, transit_interval_minutes=35
    )
    assert result.assignment_id == assignment.id
    assert result.transit_interval_minutes == 35
    assert result.transit_interval_overridden is True
    entry = audit_port.record.await_args.args[0]
    assert entry.action == "OVERRIDE_TRANSIT_INTERVAL"
    assert entry.entity_id == assignment.id
    assert entry.user_id == USER_ID
    assert entry.old_values == {
        "transit_interval_minutes": 45,
        "transit_interval_overridden": False,
    }


def test_missing_assignment_raises() -> None:
    use_case, assignments, events, audit_port = _use_case(None, None)
    with pytest.raises(ResourceNotFoundError):
        asyncio.run(use_case.execute(_input(uuid4())))
    events.get_by_id_for_update.assert_not_awaited()
    assignments.override_transit_interval.assert_not_awaited()
    audit_port.record.assert_not_awaited()


def test_missing_event_raises() -> None:
    assignment = _assignment(uuid4())
    use_case, assignments, _events, audit_port = _use_case(assignment, None)
    with pytest.raises(ResourceNotFoundError):
        asyncio.run(use_case.execute(_input(assignment.id)))
    assignments.override_transit_interval.assert_not_awaited()
    audit_port.record.assert_not_awaited()


@pytest.mark.parametrize(
    "status",
    [EventStatus.IN_PROGRESS, EventStatus.EXTENDED, EventStatus.SETTLED, EventStatus.CANCELLED],
)
def test_started_or_finished_event_raises_invalid_state(status: EventStatus) -> None:
    event = make_event(status=status)
    assignment = _assignment(event.id)
    use_case, assignments, _events, audit_port = _use_case(assignment, event)

    with pytest.raises(InvalidEventStateError):
        asyncio.run(use_case.execute(_input(assignment.id)))
    assignments.override_transit_interval.assert_not_awaited()
    audit_port.record.assert_not_awaited()


@pytest.mark.parametrize(
    "status",
    [EventStatus.AWAITING_SIGNATURE, EventStatus.SCHEDULED, EventStatus.AWAITING_BALANCE],
)
def test_event_before_start_allows_override(status: EventStatus) -> None:
    event = make_event(status=status)
    assignment = _assignment(event.id)
    use_case, assignments, _events, _audit_port = _use_case(assignment, event)
    assignments.override_transit_interval.return_value = CrewAssignmentDTO(
        id=assignment.id,
        event_id=event.id,
        crew_id=assignment.crew_id,
        transit_interval_minutes=35,
        transit_interval_overridden=True,
    )

    result = asyncio.run(use_case.execute(_input(assignment.id)))
    assert result.transit_interval_overridden is True
