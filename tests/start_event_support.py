"""Dobles con copias independientes para probar el inicio sin infraestructura."""

from copy import deepcopy
from datetime import UTC, datetime
from uuid import UUID

from app.domain.entities.event import Event
from app.domain.value_objects.money import Money
from app.infrastructure.adapters.secondary.external_services import (
    fake_payment_verification_adapter,
)

STARTED_AT = datetime(2026, 10, 15, 21, 35, tzinfo=UTC)


class FixedClock:
    def __init__(self, now: datetime = STARTED_AT) -> None:
        self.now = now
        self.calls = 0

    def utcnow(self) -> datetime:
        self.calls += 1
        return self.now


class FakeStartEventRepository:
    def __init__(self, events: tuple[Event, ...] = ()) -> None:
        self.events = {event.id: deepcopy(event) for event in events}
        self.loads: list[UUID] = []
        self.saves: list[Event] = []
        self.fail_save = False

    async def get_by_id_for_update(self, event_id: UUID) -> Event | None:
        self.loads.append(event_id)
        return deepcopy(self.events.get(event_id))

    async def save_start(self, event: Event) -> None:
        if self.fail_save:
            raise RuntimeError("No se pudo persistir")
        self.saves.append(deepcopy(event))
        self.events[event.id] = deepcopy(event)


class RecordingPayments(fake_payment_verification_adapter.FakePreShowPaymentVerificationAdapter):
    def __init__(self, totals: dict[UUID, Money] | None = None) -> None:
        super().__init__(totals)
        self.calls: list[UUID] = []

    async def get_verified_balance_total(self, event_id: UUID) -> Money:
        self.calls.append(event_id)
        return await super().get_verified_balance_total(event_id)
