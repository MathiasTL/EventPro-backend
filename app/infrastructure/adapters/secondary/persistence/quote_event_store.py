"""Unidad transaccional que crea el evento de una cotización conversacional."""

from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.catalog_dto import InventoryRequirementDTO
from app.domain.entities.quote import Quote
from app.domain.value_objects.time_window import TimeWindow
from app.infrastructure.adapters.secondary.persistence.event_provisioning import (
    add_event_with_reservations,
)
from app.infrastructure.adapters.secondary.persistence.models.event_model import EventModel
from app.infrastructure.adapters.secondary.persistence.repositories import (
    sqlalchemy_event_occupancy,
)
from app.infrastructure.adapters.secondary.persistence.repositories.sqlalchemy_quote_repository import (  # noqa: E501
    SqlAlchemyQuoteRepository,
)


class SqlAlchemyQuoteEventStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._quotes = SqlAlchemyQuoteRepository(session)

    async def lock_quote(self, quote_id: UUID) -> Quote | None:
        # Mismo candado global que las confirmaciones manuales: serializa la disponibilidad.
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": sqlalchemy_event_occupancy.AVAILABILITY_LOCK_KEY},
        )
        return await self._quotes.get_by_id_for_update(quote_id)

    async def existing_event(self, quote_id: UUID) -> tuple[UUID, str] | None:
        row = (
            await self._session.execute(
                select(EventModel.id, EventModel.status).where(EventModel.quote_id == quote_id)
            )
        ).one_or_none()
        return (row[0], row[1]) if row is not None else None

    async def add_event(
        self,
        quote: Quote,
        event_id: UUID,
        window: TimeWindow,
        requirements: tuple[InventoryRequirementDTO, ...],
    ) -> None:
        amounts = quote.liquidation
        await add_event_with_reservations(
            self._session,
            event_id=event_id,
            quote_id=quote.id,
            event_date=quote.event_date,
            start_time=quote.event_time,
            address=quote.location_address,
            district=quote.location_district,
            total_amount=amounts.total_amount.amount,
            mobility_amount=amounts.mobility_amount.amount,
            advance_amount=amounts.advance_amount.amount,
            observations=quote.observations,
            window=window,
            requirements=requirements,
        )

    async def save_quote(self, quote: Quote) -> None:
        await self._quotes.save(quote)
