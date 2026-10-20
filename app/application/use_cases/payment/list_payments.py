"""Listados paginados de pagos con filtros."""

from app.application.dtos.payment_dto import PaymentFilters, PaymentPageDTO, PaymentReadDTO
from app.application.ports.output.payment_repository_port import IPaymentRepositoryPort


class ListPaymentsUseCase:
    def __init__(self, payments: IPaymentRepositoryPort) -> None:
        self._payments = payments

    async def execute(self, filters: PaymentFilters) -> PaymentPageDTO:
        items = await self._payments.list_for_payment(filters)
        total = await self._payments.count_for_payment(filters)
        ready = [
            PaymentReadDTO(
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
            for item in items
        ]
        return PaymentPageDTO(
            items=ready, page=filters.page, page_size=filters.page_size, total=total
        )
