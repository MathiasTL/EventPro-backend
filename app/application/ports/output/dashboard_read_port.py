from typing import Protocol

from app.domain.value_objects.dashboard import DashboardReadData, DashboardWindow


class IExecutiveDashboardReadPort(Protocol):
    async def get_dashboard(self, window: DashboardWindow) -> DashboardReadData:
        """Lee agregados coherentes; rechaza instantáneas ausentes o importes inválidos."""
