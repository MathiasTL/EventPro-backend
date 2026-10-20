"""Repositorio de pagos con SQLAlchemy sobre PostgreSQL."""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.payment_dto import PaymentFilters
from app.domain.entities.payment import Payment, PaymentConcept, PaymentValidationStatus
from app.infrastructure.adapters.secondary.persistence.mappers.payment_mapper import (
    payment_to_domain,
    payment_to_model,
)
from app.infrastructure.adapters.secondary.persistence.models.payment_model import PaymentModel


class SqlAlchemyPaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, payment: Payment) -> Payment:
        existing = await self._session.get(PaymentModel, payment.id)
        if existing is None:
            self._session.add(payment_to_model(payment))
        else:
            existing.quote_id = payment.quote_id
            existing.event_id = payment.event_id
            existing.concept = payment.concept.value
            existing.payment_method = payment.payment_method.value
            existing.amount = payment.amount.amount
            existing.evidence_path = payment.evidence_path
            existing.transaction_reference = payment.transaction_reference
            existing.validation_status = payment.validation_status.value
            existing.rejection_reason = payment.rejection_reason
            existing.verified_by_user_id = payment.verified_by_user_id
            existing.verified_at = payment.verified_at
            existing.registered_by_user_id = payment.registered_by_user_id
            existing.audit_status = payment.audit_status.value if payment.audit_status else None
            existing.audited_by_user_id = payment.audited_by_user_id
            existing.audited_at = payment.audited_at
            existing.audit_notes = payment.audit_notes
        await self._session.commit()
        return payment

    async def get_by_id(self, payment_id: UUID) -> Payment | None:
        row = await self._session.get(PaymentModel, payment_id)
        return payment_to_domain(row) if row is not None else None

    def _apply_filters(self, stmt: Select[Any], filters: PaymentFilters) -> Select[Any]:
        if filters.validation_status is not None:
            stmt = stmt.where(PaymentModel.validation_status == filters.validation_status.value)
        if filters.concept is not None:
            stmt = stmt.where(PaymentModel.concept == filters.concept.value)
        if filters.audit_status is not None:
            stmt = stmt.where(PaymentModel.audit_status == filters.audit_status.value)
        if filters.quote_id is not None:
            stmt = stmt.where(PaymentModel.quote_id == filters.quote_id)
        if filters.event_id is not None:
            stmt = stmt.where(PaymentModel.event_id == filters.event_id)
        if filters.from_date is not None:
            stmt = stmt.where(PaymentModel.created_at >= filters.from_date)
        if filters.to_date is not None:
            stmt = stmt.where(PaymentModel.created_at <= filters.to_date)
        return stmt

    async def list_for_payment(self, filters: PaymentFilters) -> Sequence[Payment]:
        stmt = select(PaymentModel).order_by(PaymentModel.created_at.desc())
        stmt = self._apply_filters(stmt, filters)
        page_size = max(1, min(filters.page_size, 100))
        stmt = stmt.offset((max(1, filters.page) - 1) * page_size).limit(page_size)
        result = await self._session.execute(stmt)
        return tuple(payment_to_domain(row) for row in result.scalars().all())

    async def count_for_payment(self, filters: PaymentFilters) -> int:
        stmt = select(func.count()).select_from(PaymentModel)
        stmt = self._apply_filters(stmt, filters)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def find_active_advance(self, quote_id: UUID) -> Payment | None:
        stmt = (
            select(PaymentModel)
            .where(
                PaymentModel.quote_id == quote_id,
                PaymentModel.concept == PaymentConcept.ADVANCE.value,
                PaymentModel.validation_status.in_(
                    [
                        PaymentValidationStatus.PENDING_VERIFICATION.value,
                        PaymentValidationStatus.REQUIRES_MANUAL_APPROVAL.value,
                        PaymentValidationStatus.REFUND_PENDING.value,
                    ]
                ),
            )
            .order_by(PaymentModel.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return payment_to_domain(row) if row is not None else None
