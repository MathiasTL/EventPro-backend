from typing import Protocol

from app.application.dtos.event_occupancy_dto import EventOccupancy
from app.domain.entities.event import Event


class IEventOccupancyPort(Protocol):
    async def lock_availability(self) -> None:
        """Serializa comprobación y escritura de ocupación hasta commit o rollback."""

    async def load_occupancy(self, event: Event, added_minutes: int) -> EventOccupancy:
        """Lee otras ventanas operativas y la ocupación propuesta de recursos."""
