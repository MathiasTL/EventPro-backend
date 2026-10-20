from decimal import Decimal
from uuid import uuid4

import pytest

from app.application.dtos.financial_dto import FinancialPnlRequest
from app.application.use_cases.event.settle_event import SettleEventUseCase
from app.application.use_cases.financial.get_financial_pnl import GetFinancialPnlUseCase
from app.domain.exceptions.financial_exceptions import FinancialDataInconsistentError
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError, ValidationError
from app.domain.value_objects.financial_reporting import FinancialTotals, PeriodType
from app.domain.value_objects.money import Money
from tests.application.test_event_extensions import setup
from tests.start_event_support import STARTED_AT, FixedClock


class ReadPort:
    def __init__(self):
        self.periods = []
        self.error = None

    async def get_totals(self, period):
        self.periods.append(period)
        if self.error:
            raise self.error
        return FinancialTotals(
            10,
            Money(Decimal(10000)),
            Money(Decimal(4000)),
            Money(Decimal(1000)),
            Money(Decimal(500)),
        )


async def test_report_maps_domain_calculation():
    port = ReadPort()
    result = await GetFinancialPnlUseCase(port).execute(
        FinancialPnlRequest(PeriodType.WEEKLY, 2026, week=42)
    )
    assert result.period == "2026-W42"
    assert result.total_events_settled == 10
    assert result.gross_revenue == Decimal(10000)
    assert result.direct_costs.total_costs == Decimal(5500)
    assert result.net_profit == Decimal(4500)
    assert result.profit_margin_percentage == Decimal("45.00")


async def test_invalid_period_never_reads_persistence():
    port = ReadPort()
    with pytest.raises(ValidationError):
        await GetFinancialPnlUseCase(port).execute(FinancialPnlRequest(PeriodType.MONTHLY, 2026))
    assert port.periods == []


async def test_inconsistent_report_is_not_silently_returned():
    port = ReadPort()
    port.error = FinancialDataInconsistentError("Missing snapshot")
    with pytest.raises(FinancialDataInconsistentError):
        await GetFinancialPnlUseCase(port).execute(
            FinancialPnlRequest(PeriodType.MONTHLY, 2026, month=10)
        )


async def test_settlement_records_costs_and_clock_with_event():
    event, actor, repo, _, crews = setup()
    await SettleEventUseCase(repo, crews, FixedClock()).execute(event.id, actor)
    assert repo.cost_reads == [event.id]
    assert repo.snapshots[event.id].recorded_at == STARTED_AT
    assert repo.snapshots[event.id].gross_revenue == Money(Decimal("1080.50"))


@pytest.mark.parametrize("failure", ["costs", "save", "missing"])
async def test_settlement_rolls_back_on_rejected_operation(failure):
    event, actor, repo, _, crews = setup()
    if failure == "costs":

        async def fail(event_id):
            raise FinancialDataInconsistentError("Invalid costs")

        repo.get_settlement_costs = fail
    if failure == "save":
        repo.fail_save = True
    error = {
        "costs": FinancialDataInconsistentError,
        "save": RuntimeError,
        "missing": ResourceNotFoundError,
    }[failure]
    with pytest.raises(error):
        await SettleEventUseCase(repo, crews, FixedClock()).execute(
            uuid4() if failure == "missing" else event.id, actor
        )
    assert repo.rollbacks == 1
    assert repo.snapshots == {}
