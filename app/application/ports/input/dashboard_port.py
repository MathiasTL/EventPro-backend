from typing import Protocol

from app.application.dtos.dashboard_dto import ExecutiveDashboardDTO, ExecutiveDashboardRequest


class IGetExecutiveDashboardPort(Protocol):
    async def execute(self, request: ExecutiveDashboardRequest) -> ExecutiveDashboardDTO: ...
