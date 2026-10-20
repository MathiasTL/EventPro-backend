"""Fakes temporales de E1/E3 para Slice 1; no leen ni escriben tablas externas.

Los mapas se inyectan al construir el adaptador. La aplicación solo conoce los
puertos, de modo que E1/E3 podrán reemplazarlos por lecturas reales en DI.
"""

from collections.abc import Mapping
from uuid import UUID

from app.application.dtos.event_schedule_dto import CrewScheduleDTO, QuoteScheduleDTO

_PENDING_DETAILS = QuoteScheduleDTO(
    client_name="Cliente pendiente de integración",
    package_name="Paquete pendiente de integración",
    theme_name="Temática pendiente de integración",
)


class FakeQuoteScheduleReadAdapter:
    def __init__(self, details_by_quote: Mapping[UUID, QuoteScheduleDTO] | None = None) -> None:
        self._details = dict(details_by_quote or {})

    async def get_details(self, quote_ids: frozenset[UUID]) -> Mapping[UUID, QuoteScheduleDTO]:
        return {quote_id: self._details.get(quote_id, _PENDING_DETAILS) for quote_id in quote_ids}


class FakeCrewScheduleReadAdapter:
    def __init__(
        self,
        *,
        crews_by_event: Mapping[UUID, tuple[CrewScheduleDTO, ...]] | None = None,
        assigned_events_by_user: Mapping[UUID, frozenset[UUID]] | None = None,
    ) -> None:
        self._crews = dict(crews_by_event or {})
        self._assigned_events = dict(assigned_events_by_user or {})

    async def get_assigned_event_ids(self, user_id: UUID) -> frozenset[UUID]:
        return self._assigned_events.get(user_id, frozenset())

    async def get_crews(
        self, event_ids: frozenset[UUID]
    ) -> Mapping[UUID, tuple[CrewScheduleDTO, ...]]:
        return {event_id: self._crews.get(event_id, ()) for event_id in event_ids}
