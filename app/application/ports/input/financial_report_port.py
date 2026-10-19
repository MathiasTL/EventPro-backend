from typing import Protocol

from app.application.dtos.financial_dto import FinancialPnlDTO, FinancialPnlRequest


class IGetFinancialPnlPort(Protocol):
    async def execute(self, request: FinancialPnlRequest) -> FinancialPnlDTO: ...
