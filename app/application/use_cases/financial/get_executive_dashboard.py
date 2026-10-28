from app.application.dtos.dashboard_dto import (
    DistrictMetricDTO,
    ExecutiveDashboardDTO,
    ExecutiveDashboardRequest,
    ExtraRankingDTO,
    MonthlyProfitDTO,
    PackageMetricDTO,
    ProfitComparisonDTO,
    ThemeMetricDTO,
)
from app.application.ports.output.dashboard_read_port import IExecutiveDashboardReadPort
from app.domain.services.dashboard_reporting import DashboardReportingService
from app.domain.value_objects.dashboard import DashboardWindow

UNTAGGED_THEME_LABEL = "Sin temática"


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
            tuple(
                PackageMetricDTO(row.package_id, row.name, row.events)
                for row in result.events_by_package
            ),
            tuple(
                ThemeMetricDTO(row.theme_id, row.name or UNTAGGED_THEME_LABEL, row.events)
                for row in result.events_by_theme
            ),
            tuple(
                ExtraRankingDTO(row.extra_id, row.name, row.times_hired)
                for row in result.top_extras
            ),
            tuple(
                DistrictMetricDTO(row.district, row.events, row.net_profit.amount)
                for row in result.events_by_district
            ),
        )
