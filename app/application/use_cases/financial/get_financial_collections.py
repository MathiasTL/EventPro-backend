from app.application.dtos.financial_dto import FinancialCollectionsDTO, FinancialPnlRequest
from app.application.ports.output.financial_read_port import IFinancialReportReadPort
from app.domain.value_objects.financial_reporting import AccountingPeriod


class GetFinancialCollectionsUseCase:
    def __init__(self, reports: IFinancialReportReadPort) -> None:
        self._reports = reports

    async def execute(self, request: FinancialPnlRequest) -> FinancialCollectionsDTO:
        period = AccountingPeriod.create(
            request.period_type, request.year, month=request.month, week=request.week
        )
        totals = await self._reports.get_collections(period)
        return FinancialCollectionsDTO(
            period.label,
            totals.collected,
            totals.pending_verification,
            totals.refunds,
            totals.receivable,
        )
