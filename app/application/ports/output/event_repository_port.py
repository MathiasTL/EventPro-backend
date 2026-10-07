from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from app.application.dtos.event_extension_dto import VerifiedExtensionTotals
from app.application.dtos.event_schedule_dto import EventScheduleFilters
from app.application.ports.output.event_occupancy_port import IEventOccupancyPort
from app.domain.entities.event import Event
from app.domain.entities.event_extension import EventExtension
from app.domain.entities.payment import Payment


class IEventRepositoryPort(IEventOccupancyPort, Protocol):
    async def rollback_operation(self) -> None:
        """Libera la transacción y sus bloqueos tras una operación rechazada."""

    async def can_discard_extension_evidence(self, payment_id: UUID) -> bool:
        """Confirma que el pago no quedó persistido antes de eliminar su evidencia."""

    async def save_extension(
        self, event: Event, extension: EventExtension, payment: Payment
    ) -> None:
        """Confirma pago, extensión y acumulados juntos; revierte si falla."""

    async def get_verified_extension_totals(self, event_id: UUID) -> VerifiedExtensionTotals:
        """Comprueba vínculos, importes y cobros EXTENSION y devuelve sus totales."""

    async def save_settlement(self, event: Event) -> None:
        """Confirma la liquidación o revierte la transacción."""

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
