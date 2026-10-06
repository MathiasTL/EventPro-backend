from collections.abc import Mapping
from typing import Protocol
from uuid import UUID

from app.application.dtos.event_schedule_dto import QuoteScheduleDTO


class IQuoteScheduleReadPort(Protocol):
    async def get_details(self, quote_ids: frozenset[UUID]) -> Mapping[UUID, QuoteScheduleDTO]:
        """Enriquece cada cotización solicitada con cliente, paquete y temática."""
