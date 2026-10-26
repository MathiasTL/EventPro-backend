from app.application.dtos.dashboard_dto import (
    DistrictMetricDTO,
    ExecutiveDashboardDTO,
    ExecutiveDashboardRequest,
    MonthlyProfitDTO,
    ProfitComparisonDTO,
)
from app.application.ports.output.dashboard_read_port import IExecutiveDashboardReadPort
from app.domain.services.dashboard_reporting import DashboardReportingService
from app.domain.value_objects.dashboard import DashboardWindow


class GetExecutiveDashboardUseCase:
    def __init__(self, reports: IExecutiveDashboardReadPort) -> None:
        self._reports = reports

    async def execute(self, request: ExecutiveDashboardRequest) -> ExecutiveDashboardDTO:
        window = DashboardWindow.create(request.year, request.month, request.compare_months)
        result = DashboardReportingService.build(window, await self._reports.get_dashboard(window))
        comparison = result.net_profit_comparison
        return ExecutiveDashboardDTO(
            result.period,
            tuple(
                MonthlyProfitDTO(row.period, row.net_profit.amount)
                for row in result.net_profit_by_month
            ),
            ProfitComparisonDTO(
                comparison.previous_period,
                comparison.current_net_profit.amount,
                comparison.previous_net_profit.amount,
                comparison.absolute_change.amount,
                comparison.percentage_change,
            ),
            result.events_by_package,
            result.events_by_theme,
            result.top_extras,
            tuple(
                DistrictMetricDTO(row.district, row.events, row.net_profit.amount)
                for row in result.events_by_district
            ),
        )
