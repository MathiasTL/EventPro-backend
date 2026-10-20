"""US-12: verificar, rechazar o marcar revisión manual del adelanto."""

from datetime import UTC, datetime

from app.application.dtos.payment_dto import VerifyPaymentDTO, VerifyPaymentInput
from app.application.ports.output.payment_repository_port import IPaymentRepositoryPort
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError, ValidationError


class VerifyPaymentUseCase:
    def __init__(self, payments: IPaymentRepositoryPort) -> None:
        self._payments = payments

    async def execute(self, dto: VerifyPaymentInput) -> VerifyPaymentDTO:
        payment = await self._payments.get_by_id(dto.payment_id)
        if payment is None:
            raise ResourceNotFoundError("Pago no encontrado")
        action = dto.action.upper()
        if action == "VERIFIED":
            payment.verify(
                verified_by_user_id=dto.verified_by_user_id,
                event_id=dto.event_id,
                verified_at=datetime.now(UTC),
            )
        elif action == "REJECTED":
            if not dto.rejection_reason or not dto.rejection_reason.strip():
                raise ValidationError("rejection_reason es obligatorio al rechazar")
            payment.reject(reason=dto.rejection_reason, rejected_at=datetime.now(UTC))
        else:
            raise ValidationError("action debe ser VERIFIED o REJECTED")
        await self._payments.save(payment)
        return VerifyPaymentDTO(
            payment_id=payment.id,
            validation_status=payment.validation_status,
            rejection_reason=payment.rejection_reason,
        )
