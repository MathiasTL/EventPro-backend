"""Repositorio de pagos sobre PostgreSQL (SQLAlchemy 2.0 async).

Implementa ``IPaymentRepository`` (RF-11, RF-12, US-11, US-12). Traduce filtros
del DTO y devuelve entidades/DTOs de dominio sin exponer modelos ORM.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.payment_dto import PaymentFilterDTO, PaymentReadDTO
from app.application.ports.output.payment_port import IPaymentRepository
from app.domain.entities.payment import Payment, ValidationStatus
from app.infrastructure.adapters.secondary.persistence.mappers import payment_mapper
from app.infrastructure.adapters.secondary.persistence.models.payment_models import (
    PaymentModel,
)

_ACTIVE_ADVANCE_STATUSES = (
    ValidationStatus.PENDING_VERIFICATION,
    ValidationStatus.REQUIRES_MANUAL_APPROVAL,
    ValidationStatus.VERIFIED,
)


class SqlAlchemyPaymentRepository(IPaymentRepository):
    """Persistencia de pagos sobre PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, payment: Payment) -> Payment:
        existing = await self._session.get(PaymentModel, payment.id)
        if existing is None:
            self._session.add(payment_mapper.payment_to_model(payment))
        else:
            payment_mapper.sync_model(existing, payment)
        await self._session.flush()
        return payment

    async def get(self, payment_id: UUID) -> Payment | None:
        model = await self._session.get(PaymentModel, payment_id)
        return payment_mapper.model_to_entity(model) if model is not None else None

    def _apply_filters(self, filters: PaymentFilterDTO) -> list:
        conditions = []
        if filters.validation_status is not None:
            conditions.append(PaymentModel.validation_status == filters.validation_status.value)
        if filters.concept is not None:
            conditions.append(PaymentModel.concept == filters.concept.value)
        if filters.audit_status is not None:
            conditions.append(PaymentModel.audit_status == filters.audit_status.value)
        if filters.quote_id is not None:
            conditions.append(PaymentModel.quote_id == filters.quote_id)
        if filters.event_id is not None:
            conditions.append(PaymentModel.event_id == filters.event_id)
        if filters.from_date is not None:
            conditions.append(PaymentModel.created_at >= filters.from_date)
        if filters.to_date is not None:
            conditions.append(PaymentModel.created_at <= filters.to_date)
        return conditions

    async def list(self, filters: PaymentFilterDTO) -> Sequence[PaymentReadDTO]:
        stmt = select(PaymentModel).order_by(PaymentModel.created_at.desc())
        for condition in self._apply_filters(filters):
            stmt = stmt.where(condition)
        page_size = max(1, min(filters.page_size, 100))
        stmt = stmt.offset((max(1, filters.page) - 1) * page_size).limit(page_size)
        result = await self._session.execute(stmt)
        return tuple(payment_mapper.payment_to_dto(model) for model in result.scalars().all())

    async def count(self, filters: PaymentFilterDTO) -> int:
        stmt = select(func.count()).select_from(PaymentModel)
        for condition in self._apply_filters(filters):
            stmt = stmt.where(condition)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def find_active_advance(self, quote_id: UUID) -> Payment | None:
        stmt = (
            select(PaymentModel)
            .where(
                PaymentModel.quote_id == quote_id,
                PaymentModel.concept == "ADVANCE",
                PaymentModel.validation_status.in_(
                    [status.value for status in _ACTIVE_ADVANCE_STATUSES]
                ),
            )
            .order_by(PaymentModel.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        model = result.scalars().first()
        return payment_mapper.model_to_entity(model) if model is not None else None
