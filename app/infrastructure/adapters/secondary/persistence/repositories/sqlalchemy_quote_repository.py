"""Repositorio de cotizaciones con SQLAlchemy. No confirma: la transacción es del llamador."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.page_dto import PageDTO
from app.application.dtos.quote_dto import (
    ClientSummaryDTO,
    ListQuotesFilter,
    QuoteDetailDTO,
    QuoteExtraDetailDTO,
    QuoteListItemDTO,
    QuotePackageDTO,
    QuotePaymentDTO,
    QuoteThemeDTO,
)
from app.domain.entities.payment import PaymentConcept, PaymentValidationStatus
from app.domain.entities.quote import Quote, QuoteStatus
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError
from app.infrastructure.adapters.secondary.persistence.mappers.quote_mapper import (
    apply_quote_to_model,
    quote_to_domain,
    quote_to_model,
)
from app.infrastructure.adapters.secondary.persistence.models.catalog_models import (
    ExtraModel,
    PackageModel,
    ThemeModel,
)
from app.infrastructure.adapters.secondary.persistence.models.client_model import ClientModel
from app.infrastructure.adapters.secondary.persistence.models.event_model import EventModel
from app.infrastructure.adapters.secondary.persistence.models.payment_model import PaymentModel
from app.infrastructure.adapters.secondary.persistence.models.quote_model import QuoteModel


class SqlAlchemyQuoteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, quote: Quote) -> Quote:
        self._session.add(quote_to_model(quote))
        await self._session.flush()
        return quote

    async def save(self, quote: Quote) -> Quote:
        row = await self._session.get(QuoteModel, quote.id)
        if row is None:
            raise ResourceNotFoundError(f"La cotización {quote.id} no existe")
        apply_quote_to_model(row, quote)
        await self._session.flush()
        return quote

    async def get_by_id(self, quote_id: UUID) -> Quote | None:
        row = await self._session.get(QuoteModel, quote_id)
        return quote_to_domain(row) if row is not None else None

    async def get_by_id_for_update(self, quote_id: UUID) -> Quote | None:
        stmt = (
            select(QuoteModel)
            .where(QuoteModel.id == quote_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return quote_to_domain(row) if row is not None else None

    async def get_detail(self, quote_id: UUID) -> QuoteDetailDTO | None:
        quote = await self.get_by_id(quote_id)
        if quote is None:
            return None
        client = await self._session.get(ClientModel, quote.client_id)
        package = await self._session.get(PackageModel, quote.package_id)
        if client is None or package is None:
            raise ResourceNotFoundError("Datos de la cotización incompletos")
        theme = await self._session.get(ThemeModel, quote.theme_id) if quote.theme_id else None
        names = dict(
            (
                await self._session.execute(
                    select(ExtraModel.id, ExtraModel.name).where(
                        ExtraModel.id.in_([e.extra_id for e in quote.extras])
                    )
                )
            )
            .tuples()
            .all()
        )
        payments = (
            await self._session.scalars(
                select(PaymentModel)
                .where(PaymentModel.quote_id == quote.id)
                .order_by(PaymentModel.id)
            )
        ).all()
        event_id = await self._session.scalar(
            select(EventModel.id).where(EventModel.quote_id == quote.id)
        )
        amounts = quote.liquidation
        # El precio vendido no cambia cuando se edita posteriormente el catálogo.
        base_price = amounts.services_subtotal.amount - sum(
            (e.subtotal.amount for e in quote.extras), Decimal(0)
        )
        return QuoteDetailDTO(
            quote_id=quote.id,
            client=ClientSummaryDTO(client.id, client.full_name, client.phone),
            source=quote.source,
            event_date=quote.event_date,
            event_time=quote.event_time,
            location_address=quote.location_address,
            location_district=quote.location_district,
            package=QuotePackageDTO(package.id, package.name, base_price),
            theme=QuoteThemeDTO(theme.id, theme.name) if theme else None,
            extras=tuple(
                QuoteExtraDetailDTO(
                    e.extra_id,
                    names[e.extra_id],
                    e.quantity,
                    e.unit_price.amount,
                    e.subtotal.amount,
                )
                for e in quote.extras
            ),
            services_subtotal=amounts.services_subtotal.amount,
            final_mobility_amount=amounts.mobility_amount.amount,
            mobility_overridden=quote.mobility_overridden,
            total_amount=amounts.total_amount.amount,
            advance_amount=amounts.advance_amount.amount,
            pending_balance=amounts.pending_balance.amount,
            status=quote.status,
            sent_at=quote.sent_at,
            expires_at=quote.expires_at,
            observations=quote.observations,
            payments=tuple(
                QuotePaymentDTO(
                    p.id, PaymentConcept(p.concept), PaymentValidationStatus(p.validation_status)
                )
                for p in payments
            ),
            event_id=event_id,
        )

    async def list_quotes(self, filters: ListQuotesFilter) -> PageDTO[QuoteListItemDTO]:
        query = (
            select(QuoteModel, ClientModel, PackageModel.name)
            .join(ClientModel, ClientModel.id == QuoteModel.client_id)
            .join(PackageModel, PackageModel.id == QuoteModel.package_id)
        )
        if filters.status is not None:
            query = query.where(QuoteModel.status == filters.status.value)
        if filters.client_id is not None:
            query = query.where(QuoteModel.client_id == filters.client_id)
        if filters.from_date is not None:
            query = query.where(QuoteModel.event_date >= filters.from_date)
        if filters.to_date is not None:
            query = query.where(QuoteModel.event_date <= filters.to_date)
        total = await self._session.scalar(select(func.count()).select_from(query.subquery()))
        rows = (
            await self._session.execute(
                query.order_by(QuoteModel.sent_at.desc(), QuoteModel.id.desc())
                .offset((filters.page - 1) * filters.page_size)
                .limit(filters.page_size)
            )
        ).all()
        return PageDTO(
            items=tuple(
                QuoteListItemDTO(
                    q.id,
                    ClientSummaryDTO(c.id, c.full_name, c.phone),
                    q.event_date,
                    name,
                    q.total_amount,
                    QuoteStatus(q.status),
                    q.expires_at,
                )
                for q, c, name in rows
            ),
            page=filters.page,
            page_size=filters.page_size,
            total=total or 0,
        )

    async def has_payment_in_review(self, quote_id: UUID) -> bool:
        query = (
            select(PaymentModel.id)
            .where(
                PaymentModel.quote_id == quote_id,
                PaymentModel.validation_status.in_(
                    ["PENDING_VERIFICATION", "REQUIRES_MANUAL_APPROVAL"]
                ),
            )
            .exists()
        )
        return bool(await self._session.scalar(select(query)))

    async def find_due(self, now: datetime) -> tuple[Quote, ...]:
        reviewing = (
            select(PaymentModel.id)
            .where(
                PaymentModel.quote_id == QuoteModel.id,
                PaymentModel.validation_status.in_(
                    ["PENDING_VERIFICATION", "REQUIRES_MANUAL_APPROVAL"]
                ),
            )
            .exists()
        )
        rows = await self._session.scalars(
            select(QuoteModel)
            .where(
                QuoteModel.status.in_(["SENT", "PAYMENT_STARTED"]),
                QuoteModel.expires_at <= now,
                ~reviewing,
            )
            .order_by(QuoteModel.id)
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
        return tuple(quote_to_domain(q) for q in rows)
