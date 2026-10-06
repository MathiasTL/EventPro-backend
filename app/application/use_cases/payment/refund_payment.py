"""US-12/RF-12: confirmar devolución de un adelanto en reembolso."""

from uuid import UUID

from app.application.dtos.payment_dto import RefundPaymentDTO
from app.application.ports.output.payment_repository_port import IPaymentRepositoryPort
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError


class RefundPaymentUseCase:
    def __init__(self, payments: IPaymentRepositoryPort) -> None:
        self._payments = payments

    async def execute(self, payment_id: UUID) -> RefundPaymentDTO:
        payment = await self._payments.get_by_id(payment_id)
        if payment is None:
            raise ResourceNotFoundError("Pago no encontrado")
        payment.confirm_refund()
        await self._payments.save(payment)
        return RefundPaymentDTO(payment_id=payment.id, validation_status=payment.validation_status)
