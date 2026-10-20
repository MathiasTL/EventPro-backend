"""Fake temporal de E5, configurable por event_id y sin acceso a PostgreSQL."""

from collections.abc import Mapping
from uuid import UUID

from app.domain.value_objects.money import Money


class FakePreShowPaymentVerificationAdapter:
    def __init__(self, verified_totals: Mapping[UUID, Money] | None = None) -> None:
        self._totals = dict(verified_totals or {})

    async def get_verified_balance_total(self, event_id: UUID) -> Money:
        return self._totals.get(event_id, Money.zero())
