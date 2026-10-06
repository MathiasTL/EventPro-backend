from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from app.application.dtos.event_schedule_dto import EventScheduleFilters
from app.domain.entities.event import Event


class IEventRepositoryPort(Protocol):
    async def get_by_id_for_update(self, event_id: UUID) -> Event | None:
        """Carga y bloquea el evento hasta confirmar o revertir la sesión."""

    async def save_start(self, event: Event) -> None:
        """Persiste estado, saldo verificado e inicio real en una transacción."""

    async def list_for_schedule(
        self, filters: EventScheduleFilters, *, event_ids: frozenset[UUID] | None = None
    ) -> Sequence[Event]:
        """Filtra por fechas/estado; None permite todos los IDs, conjunto vacío ninguno.

        Orden ascendente por event_date, start_time e id; límites inclusivos.
        """
