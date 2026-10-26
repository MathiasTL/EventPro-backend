from decimal import Decimal
from uuid import uuid4

import pytest

from app.application.dtos.dashboard_dto import ExecutiveDashboardRequest
from app.application.use_cases.financial.get_executive_dashboard import GetExecutiveDashboardUseCase
from app.domain.exceptions.financial_exceptions import FinancialDataInconsistentError
from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.dashboard import (
    DashboardReadData,
    DistrictTotals,
    ExtraRanking,
    MonthlyTotals,
    PackageMetric,
    ThemeMetric,
)
from tests.dashboard_support import DashboardReadPort, totals


async def test_maps_domain_to_dto_and_reads_once():
    package, theme, extra = uuid4(), uuid4(), uuid4()
    port = DashboardReadPort(
        DashboardReadData(
            months=(
                MonthlyTotals("2026-09", totals("100")),
                MonthlyTotals("2026-10", totals("125")),
            ),
            packages=(PackageMetric(package, "Paquete", 1),),
            themes=(ThemeMetric(theme, "Selva", 1),),
            extras=(ExtraRanking(extra, "Gorila", 3),),
            districts=(DistrictTotals("Lima", totals("125")),),
        )
    )
    result = await GetExecutiveDashboardUseCase(port).execute(ExecutiveDashboardRequest(2026, 10))
    assert len(port.windows) == 1 and len(port.windows[0].periods) == 4
    assert result.period == "2026-10"
    assert result.net_profit_by_month[-1].net_profit == Decimal("125.00")
    assert result.net_profit_comparison.percentage_change == Decimal("25.00")
    assert result.events_by_package[0].package_id == package
    assert result.events_by_theme[0].theme_id == theme
    assert result.top_extras[0].times_hired == 3
    assert result.events_by_district[0].net_profit == Decimal("125.00")


async def test_invalid_request_never_reads():
    port = DashboardReadPort()
    with pytest.raises(ValidationError):
        await GetExecutiveDashboardUseCase(port).execute(ExecutiveDashboardRequest(1, 1))
    assert port.windows == []


async def test_inconsistent_data_is_propagated():
    port = DashboardReadPort()
    port.error = FinancialDataInconsistentError("Missing snapshot")
    with pytest.raises(FinancialDataInconsistentError):
        await GetExecutiveDashboardUseCase(port).execute(ExecutiveDashboardRequest(2026, 10))
