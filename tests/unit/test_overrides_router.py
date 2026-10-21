"""Pruebas unitarias de PATCH /overrides/quotes/{id}/mobility y

PATCH /overrides/crew-assignments/{id}/transit-interval (RF-21, RF-22, US-19, US-20).
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.application.dtos.crew_assignment_dto import CrewAssignmentDTO
from app.application.services.audit_service import AuditService
from app.application.use_cases.crew.override_transit_interval import (
    OverrideCrewTransitIntervalUseCase,
)
from app.application.use_cases.quote.override_mobility import OverrideQuoteMobilityUseCase
from app.core.config import get_settings
from app.core.security import create_access_token
from app.domain.entities.audit_log import AuditLog
from app.domain.entities.quote import Quote, QuoteStatus
from app.domain.value_objects.event_status import EventStatus
from app.domain.value_objects.role import Role
from app.infrastructure.di import containers
from app.main import create_app
from tests.auth_support import install, set_role
from tests.domain.financial_support import default_engine
from tests.domain.quote_support import make_quote
from tests.event_support import make_event

MOBILITY_PATH = "/api/v1/overrides/quotes/{quote_id}/mobility"
TRANSIT_PATH = "/api/v1/overrides/crew-assignments/{assignment_id}/transit-interval"
USER_ID = uuid4()


class FakeQuoteRepository:
    def __init__(self, quote: Quote) -> None:
        self._quote = quote

    async def add(self, quote: Quote) -> Quote:
        self._quote = quote
        return quote

    async def save(self, quote: Quote) -> Quote:
        self._quote = quote
        return quote

    async def get_by_id(self, quote_id: UUID) -> Quote | None:
        return self._quote if self._quote.id == quote_id else None


class FakeCrewAssignmentRepository:
    def __init__(self, assignment: CrewAssignmentDTO) -> None:
        self._assignment = assignment

    async def get_by_id(self, assignment_id: UUID) -> CrewAssignmentDTO | None:
        return self._assignment if self._assignment.id == assignment_id else None

    async def override_transit_interval(
        self, assignment_id: UUID, *, transit_interval_minutes: int
    ) -> CrewAssignmentDTO:
        self._assignment = CrewAssignmentDTO(
            id=self._assignment.id,
            event_id=self._assignment.event_id,
            crew_id=self._assignment.crew_id,
            transit_interval_minutes=transit_interval_minutes,
            transit_interval_overridden=True,
        )
        return self._assignment


class FakeEventRepository:
    def __init__(self, event) -> None:
        self._event = event

    async def get_by_id_for_update(self, event_id: UUID):
        return self._event if self._event.id == event_id else None


class AsyncFakePort:
    """Puerto de auditoría mínimo: las aserciones de estas pruebas no leen la bitácora."""

    async def record(self, entry: AuditLog) -> None:
        return None


def authorization(role: Role = Role.ENCARGADO) -> dict[str, str]:
    set_role(role)
    token = create_access_token(
        subject=str(USER_ID), role=role.value, secret_key=get_settings().secret_key
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def web_app() -> Iterator[FastAPI]:
    app = create_app()
    install(app)
    yield app
    app.dependency_overrides.clear()


async def _call(
    web_app: FastAPI, method: str, path: str, *, json: dict, role: Role = Role.ENCARGADO
):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=web_app), base_url="http://test"
    ) as client:
        return await client.request(method, path, headers=authorization(role), json=json)


def _install_mobility_use_case(web_app: FastAPI, quote: Quote) -> None:
    repo = FakeQuoteRepository(quote)
    use_case = OverrideQuoteMobilityUseCase(repo, default_engine(), AuditService(AsyncFakePort()))
    web_app.dependency_overrides[containers.get_override_quote_mobility_use_case] = lambda: use_case


async def test_override_mobility_returns_200_with_recalculated_totals(web_app: FastAPI) -> None:
    quote = make_quote()
    _install_mobility_use_case(web_app, quote)

    response = await _call(
        web_app,
        "PATCH",
        MOBILITY_PATH.format(quote_id=quote.id),
        json={"manual_mobility_amount": "95.00", "reason": "Peajes no computados"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mobility_amount"] == "95.00"
    assert body["mobility_overridden"] is True
    assert quote.mobility_overridden is True


async def test_override_mobility_unknown_quote_returns_404(web_app: FastAPI) -> None:
    quote = make_quote()
    _install_mobility_use_case(web_app, quote)

    response = await _call(
        web_app,
        "PATCH",
        MOBILITY_PATH.format(quote_id=uuid4()),
        json={"manual_mobility_amount": "95.00", "reason": "Peajes no computados"},
    )
    assert response.status_code == 404


async def test_override_mobility_converted_quote_returns_409(web_app: FastAPI) -> None:
    quote = make_quote()
    quote.status = QuoteStatus.CONVERTED
    _install_mobility_use_case(web_app, quote)

    response = await _call(
        web_app,
        "PATCH",
        MOBILITY_PATH.format(quote_id=quote.id),
        json={"manual_mobility_amount": "95.00", "reason": "Peajes no computados"},
    )
    assert response.status_code == 409
    assert response.json()["type"].endswith("invalid-quote-state")


async def test_override_mobility_negative_amount_returns_422(web_app: FastAPI) -> None:
    quote = make_quote()
    _install_mobility_use_case(web_app, quote)

    response = await _call(
        web_app,
        "PATCH",
        MOBILITY_PATH.format(quote_id=quote.id),
        json={"manual_mobility_amount": "-5.00", "reason": "Peajes no computados"},
    )
    assert response.status_code == 422


async def test_override_mobility_blank_reason_returns_422(web_app: FastAPI) -> None:
    quote = make_quote()
    _install_mobility_use_case(web_app, quote)

    response = await _call(
        web_app,
        "PATCH",
        MOBILITY_PATH.format(quote_id=quote.id),
        json={"manual_mobility_amount": "95.00", "reason": "   "},
    )
    assert response.status_code == 422


async def test_override_mobility_forbidden_for_operator(web_app: FastAPI) -> None:
    quote = make_quote()
    _install_mobility_use_case(web_app, quote)

    response = await _call(
        web_app,
        "PATCH",
        MOBILITY_PATH.format(quote_id=quote.id),
        json={"manual_mobility_amount": "95.00", "reason": "Peajes no computados"},
        role=Role.OPERADOR,
    )
    assert response.status_code == 403


def _install_transit_use_case(web_app: FastAPI, assignment: CrewAssignmentDTO, event) -> None:
    assignments = FakeCrewAssignmentRepository(assignment)
    events = FakeEventRepository(event)
    use_case = OverrideCrewTransitIntervalUseCase(
        assignments, events, AuditService(AsyncFakePort())
    )
    web_app.dependency_overrides[containers.get_override_crew_transit_interval_use_case] = lambda: (
        use_case
    )


async def test_override_transit_interval_returns_200(web_app: FastAPI) -> None:
    event = make_event(status=EventStatus.SCHEDULED)
    assignment = CrewAssignmentDTO(
        id=uuid4(),
        event_id=event.id,
        crew_id=uuid4(),
        transit_interval_minutes=45,
        transit_interval_overridden=False,
    )
    _install_transit_use_case(web_app, assignment, event)

    response = await _call(
        web_app,
        "PATCH",
        TRANSIT_PATH.format(assignment_id=assignment.id),
        json={"transit_interval_minutes": 35, "reason": "Ruta alterna confirmada"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body == {
        "assignment_id": str(assignment.id),
        "transit_interval_minutes": 35,
        "transit_interval_overridden": True,
    }


async def test_override_transit_interval_unknown_assignment_returns_404(web_app: FastAPI) -> None:
    event = make_event(status=EventStatus.SCHEDULED)
    assignment = CrewAssignmentDTO(
        id=uuid4(),
        event_id=event.id,
        crew_id=uuid4(),
        transit_interval_minutes=45,
        transit_interval_overridden=False,
    )
    _install_transit_use_case(web_app, assignment, event)

    response = await _call(
        web_app,
        "PATCH",
        TRANSIT_PATH.format(assignment_id=uuid4()),
        json={"transit_interval_minutes": 35, "reason": "Ruta alterna confirmada"},
    )
    assert response.status_code == 404


async def test_override_transit_interval_started_event_returns_409(web_app: FastAPI) -> None:
    event = make_event(status=EventStatus.IN_PROGRESS)
    assignment = CrewAssignmentDTO(
        id=uuid4(),
        event_id=event.id,
        crew_id=uuid4(),
        transit_interval_minutes=45,
        transit_interval_overridden=False,
    )
    _install_transit_use_case(web_app, assignment, event)

    response = await _call(
        web_app,
        "PATCH",
        TRANSIT_PATH.format(assignment_id=assignment.id),
        json={"transit_interval_minutes": 35, "reason": "Ruta alterna confirmada"},
    )
    assert response.status_code == 409
    assert response.json()["type"].endswith("invalid-event-state")


async def test_override_transit_interval_negative_minutes_returns_422(web_app: FastAPI) -> None:
    event = make_event(status=EventStatus.SCHEDULED)
    assignment = CrewAssignmentDTO(
        id=uuid4(),
        event_id=event.id,
        crew_id=uuid4(),
        transit_interval_minutes=45,
        transit_interval_overridden=False,
    )
    _install_transit_use_case(web_app, assignment, event)

    response = await _call(
        web_app,
        "PATCH",
        TRANSIT_PATH.format(assignment_id=assignment.id),
        json={"transit_interval_minutes": -1, "reason": "Ruta alterna confirmada"},
    )
    assert response.status_code == 422
