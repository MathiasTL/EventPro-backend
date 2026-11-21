from typing import Protocol
from uuid import UUID

from app.application.dtos.financial_dto import FinancialCollectionsTotalsDTO
from app.domain.value_objects.financial_reporting import (
    AccountingPeriod,
    EventDirectCosts,
    FinancialTotals,
)


class IEventFinancialReadPort(Protocol):
    async def get_settlement_costs(self, event_id: UUID) -> EventDirectCosts:
        """Lee todos los costos en una instantánea coherente de la transacción de cierre."""


class IFinancialReportReadPort(Protocol):
    async def get_totals(self, period: AccountingPeriod) -> FinancialTotals:
        """Consolida SETTLED; rechaza datos incompletos en lugar de omitir eventos."""

    async def get_collections(self, period: AccountingPeriod) -> FinancialCollectionsTotalsDTO:
        """Aggregate payment movement and outstanding event balances for a period."""
