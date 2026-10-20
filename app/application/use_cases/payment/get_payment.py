"""Detalle de Pago."""

from uuid import UUID

from app.application.dtos.payment_dto import PaymentReadDTO
from app.application.ports.output.payment_repository_port import IPaymentRepositoryPort
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError


class GetPaymentUseCase:
    def __init__(self, payments: IPaymentRepositoryPort) -> None:
        self._payments = payments

    async def execute(self, payment_id: UUID) -> PaymentReadDTO:
        item = await self._payments.get_by_id(payment_id)
        if item is None:
            raise ResourceNotFoundError("Pago no encontrado")
        return PaymentReadDTO(
            payment_id=item.id,
            quote_id=item.quote_id,
            concept=item.concept,
            payment_method=item.payment_method,
            amount=item.amount.amount,
            validation_status=item.validation_status,
            audit_status=item.audit_status,
            event_id=item.event_id,
            transaction_reference=item.transaction_reference,
            rejection_reason=item.rejection_reason,
            verified_by_user_id=item.verified_by_user_id,
            verified_at=item.verified_at,
            registered_by_user_id=item.registered_by_user_id,
            audited_by_user_id=item.audited_by_user_id,
            audited_at=item.audited_at,
            audit_notes=item.audit_notes,
            created_at=item.created_at,
        )
