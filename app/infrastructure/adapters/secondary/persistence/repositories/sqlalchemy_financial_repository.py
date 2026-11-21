from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.application.dtos.financial_dto import (
    FinancialCollectedDTO,
    FinancialCollectionsTotalsDTO,
    FinancialPendingVerificationDTO,
    FinancialReceivableDTO,
    FinancialRefundsDTO,
)
from app.core.logging import get_logger
from app.domain.exceptions.financial_exceptions import FinancialDataInconsistentError
from app.domain.value_objects.financial_reporting import (
    AccountingPeriod,
    EventDirectCosts,
    ExtraDirectCost,
    FinancialTotals,
)
from app.domain.value_objects.money import Money
from app.infrastructure.adapters.secondary.persistence.models.catalog_models import (
    ExtraModel,
    PackageModel,
)
from app.infrastructure.adapters.secondary.persistence.models.event_financial_snapshot_model import (  # noqa: E501
    EventFinancialSnapshotModel,
)
from app.infrastructure.adapters.secondary.persistence.models.event_model import EventModel
from app.infrastructure.adapters.secondary.persistence.models.payment_model import PaymentModel
from app.infrastructure.adapters.secondary.persistence.models.quote_model import (
    QuoteExtraModel,
    QuoteModel,
)

logger = get_logger(__name__)


def _money(value: Decimal) -> Money:
    if not value.is_finite() or value < 0:
        raise FinancialDataInconsistentError("Importe contable inválido en persistencia.")
    return Money(value)


class SqlAlchemyFinancialRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_settlement_costs(self, event_id: UUID) -> EventDirectCosts:
        rows = (
            await self._session.execute(
                select(
                    QuoteModel.package_id,
                    PackageModel.direct_cost.label("package_cost"),
                    QuoteModel.client_provides_mobility,
                    QuoteModel.base_mobility_amount,
                    QuoteExtraModel.id.label("line_id"),
                    QuoteExtraModel.quantity,
                    ExtraModel.id.label("extra_id"),
                    ExtraModel.direct_cost.label("extra_cost"),
                )
                .select_from(EventModel)
                .join(QuoteModel, QuoteModel.id == EventModel.quote_id)
                .join(PackageModel, PackageModel.id == QuoteModel.package_id)
                .outerjoin(QuoteExtraModel, QuoteExtraModel.quote_id == QuoteModel.id)
                .outerjoin(ExtraModel, ExtraModel.id == QuoteExtraModel.extra_id)
                .where(EventModel.id == event_id)
                .order_by(QuoteExtraModel.extra_id, QuoteExtraModel.id)
            )
        ).all()
        if not rows:
            raise FinancialDataInconsistentError("Faltan la cotización o el paquete del evento.")
        extras = []
        for row in rows:
            if row.line_id is not None:
                if row.extra_id is None:
                    raise FinancialDataInconsistentError("Falta un extra contratado.")
                extras.append(ExtraDirectCost(row.extra_id, row.quantity, _money(row.extra_cost)))
        first = rows[0]
        return EventDirectCosts(
            first.package_id,
            _money(first.package_cost),
            tuple(extras),
            Money.zero() if first.client_provides_mobility else _money(first.base_mobility_amount),
        )

    async def get_totals(self, period: AccountingPeriod) -> FinancialTotals:
        snapshot = EventFinancialSnapshotModel
        row = (
            await self._session.execute(
                select(
                    func.count(EventModel.id).label("events"),
                    func.count(EventModel.id).filter(snapshot.event_id.is_(None)).label("missing"),
                    func.array_agg(EventModel.id)
                    .filter(snapshot.event_id.is_(None))
                    .label("missing_event_ids"),
                    *(
                        func.coalesce(func.sum(column), 0).label(name)
                        for name, column in (
                            ("revenue", snapshot.gross_revenue),
                            ("packages", snapshot.fixed_packages_cost),
                            ("extras", snapshot.fixed_extras_cost),
                            ("mobility", snapshot.mobility_operational_cost),
                        )
                    ),
                )
                .select_from(EventModel)
                .outerjoin(snapshot, snapshot.event_id == EventModel.id)
                .where(
                    EventModel.status == "SETTLED",
                    EventModel.event_date >= period.start,
                    EventModel.event_date < period.end,
                )
            )
        ).one()
        if row.missing:
            logger.warning(
                "financial_data_inconsistent",
                period=period.label,
                missing_snapshots=row.missing,
                event_ids=sorted(str(event_id) for event_id in row.missing_event_ids),
            )
            raise FinancialDataInconsistentError(
                "Existen eventos liquidados sin instantánea financiera."
            )
        return FinancialTotals(
            row.events,
            _money(row.revenue),
            _money(row.packages),
            _money(row.extras),
            _money(row.mobility),
        )

    async def get_collections(self, period: AccountingPeriod) -> FinancialCollectionsTotalsDTO:
        payment = PaymentModel
        verified_date = func.timezone(
            "America/Lima", func.coalesce(payment.verified_at, payment.created_at)
        ).cast(Date)
        created_date = func.timezone("America/Lima", payment.created_at).cast(Date)
        verified = and_(
            payment.validation_status == "VERIFIED",
            verified_date >= period.start,
            verified_date < period.end,
        )
        created_in_period = and_(created_date >= period.start, created_date < period.end)

        def amount_for(*conditions: ColumnElement[bool]) -> ColumnElement[Decimal]:
            return func.coalesce(func.sum(payment.amount).filter(*conditions), 0)

        payment_row = (
            await self._session.execute(
                select(
                    amount_for(verified, payment.concept == "ADVANCE").label("advance"),
                    amount_for(verified, payment.concept == "BALANCE").label("balance"),
                    amount_for(verified, payment.concept == "EXTENSION").label("extension"),
                    amount_for(verified).label("total"),
                    func.count(payment.id).filter(verified).label("collected_count"),
                    amount_for(
                        created_in_period,
                        payment.validation_status.in_(
                            ("PENDING_VERIFICATION", "REQUIRES_MANUAL_APPROVAL")
                        ),
                    ).label("pending_amount"),
                    func.count(payment.id)
                    .filter(
                        created_in_period,
                        payment.validation_status.in_(
                            ("PENDING_VERIFICATION", "REQUIRES_MANUAL_APPROVAL")
                        ),
                    )
                    .label("pending_count"),
                    amount_for(
                        created_in_period,
                        payment.concept == "ADVANCE",
                        payment.validation_status == "REFUND_PENDING",
                    ).label("refund_pending"),
                    amount_for(
                        created_in_period,
                        payment.concept == "ADVANCE",
                        payment.validation_status == "REFUNDED",
                    ).label("refunded"),
                )
            )
        ).one()

        verified_by_quote = (
            select(
                payment.quote_id.label("quote_id"),
                func.sum(payment.amount).label("verified_amount"),
            )
            .where(payment.validation_status == "VERIFIED")
            .group_by(payment.quote_id)
            .subquery()
        )
        expected_total = func.coalesce(
            func.nullif(EventModel.final_total_amount, 0), QuoteModel.total_amount
        )
        remainder = func.greatest(
            expected_total - func.coalesce(verified_by_quote.c.verified_amount, 0), 0
        )
        receivable_row = (
            await self._session.execute(
                select(
                    func.coalesce(func.sum(remainder), 0).label("amount"),
                    func.count(EventModel.id).filter(remainder > 0).label("events_count"),
                )
                .select_from(EventModel)
                .join(QuoteModel, QuoteModel.id == EventModel.quote_id)
                .outerjoin(verified_by_quote, verified_by_quote.c.quote_id == EventModel.quote_id)
                .where(
                    EventModel.event_date >= period.start,
                    EventModel.event_date < period.end,
                    EventModel.status.not_in(("SETTLED", "CANCELLED")),
                )
            )
        ).one()
        return FinancialCollectionsTotalsDTO(
            FinancialCollectedDTO(
                payment_row.advance,
                payment_row.balance,
                payment_row.extension,
                payment_row.total,
                payment_row.collected_count,
            ),
            FinancialPendingVerificationDTO(payment_row.pending_amount, payment_row.pending_count),
            FinancialRefundsDTO(payment_row.refund_pending, payment_row.refunded),
            FinancialReceivableDTO(receivable_row.amount, receivable_row.events_count),
        )
