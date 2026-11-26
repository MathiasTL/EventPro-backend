"""Puertos para crear el evento de una cotización conversacional al verificar su adelanto."""

from typing import Protocol
from uuid import UUID

from app.application.dtos.catalog_dto import InventoryRequirementDTO
from app.domain.entities.quote import Quote
from app.domain.value_objects.time_window import TimeWindow


class IQuoteEventStore(Protocol):
    """Persistencia transaccional; nunca confirma, la transacción es del llamador."""

    async def lock_quote(self, quote_id: UUID) -> Quote | None:
        """Toma el candado global de disponibilidad y bloquea la cotización."""

    async def existing_event(self, quote_id: UUID) -> tuple[UUID, str] | None:
        """Devuelve ``(event_id, status)`` del evento de la cotización, si existe."""

    async def add_event(
        self,
        quote: Quote,
        event_id: UUID,
        window: TimeWindow,
        requirements: tuple[InventoryRequirementDTO, ...],
    ) -> None:
        """Inserta el evento ``AWAITING_SIGNATURE`` con sus reservas de inventario."""

    async def save_quote(self, quote: Quote) -> None: ...


class IQuoteEventProvisioner(Protocol):
    async def ensure_event(self, quote_id: UUID, *, check_availability: bool = True) -> UUID | None:
        """Devuelve el evento de la cotización, creándolo si falta.

        Con ``check_availability=False`` (sobrecupo autorizado) no se valida el cupo.

        Devuelve ``None`` cuando no hay disponibilidad y no se creó nada.
        """
