from typing import Protocol

from app.application.dtos.financial_dto import (
    FinancialCollectionsDTO,
    FinancialPnlDTO,
    FinancialPnlRequest,
)


class IGetFinancialPnlPort(Protocol):
    async def execute(self, request: FinancialPnlRequest) -> FinancialPnlDTO: ...


class IGetFinancialCollectionsPort(Protocol):
    async def execute(self, request: FinancialPnlRequest) -> FinancialCollectionsDTO: ...
