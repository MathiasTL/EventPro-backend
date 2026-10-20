from app.application.dtos.financial_dto import (
    FinancialDirectCostsDTO,
    FinancialPnlDTO,
    FinancialPnlRequest,
)
from app.application.ports.output.financial_read_port import IFinancialReportReadPort
from app.domain.services.financial_reporting import FinancialReportingService
from app.domain.value_objects.financial_reporting import AccountingPeriod


class GetFinancialPnlUseCase:
    def __init__(self, reports: IFinancialReportReadPort) -> None:
        self._reports = reports

    async def execute(self, request: FinancialPnlRequest) -> FinancialPnlDTO:
        period = AccountingPeriod.create(
            request.period_type, request.year, month=request.month, week=request.week
        )
        result = FinancialReportingService.consolidate(await self._reports.get_totals(period))
        totals = result.totals
        return FinancialPnlDTO(
            period.label,
            totals.total_events_settled,
            totals.gross_revenue.amount,
            FinancialDirectCostsDTO(
                totals.fixed_packages_cost.amount,
                totals.fixed_extras_cost.amount,
                totals.mobility_operational_cost.amount,
                result.total_costs.amount,
            ),
            result.net_profit.amount,
            result.profit_margin_percentage,
        )
