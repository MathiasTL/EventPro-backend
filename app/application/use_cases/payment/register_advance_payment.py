"""US-11: registrar captura del adelanto y encolar validación."""

from app.application.dtos.payment_dto import CreateAdvancePaymentInput, PaymentCreatedDTO
from app.application.ports.output.payment_repository_port import IPaymentRepositoryPort
from app.domain.entities.payment import Payment, PaymentConcept
from app.domain.exceptions.resource_exceptions import ResourceInUseError
from app.domain.value_objects.money import Money


class RegisterAdvancePaymentUseCase:
    def __init__(self, payments: IPaymentRepositoryPort) -> None:
        self._payments = payments

    async def execute(self, dto: CreateAdvancePaymentInput) -> PaymentCreatedDTO:
        if dto.amount < 0:
            raise ValueError("amount no puede ser negativo")
        existing = await self._payments.find_active_advance(dto.quote_id)
        if existing is not None:
            raise ResourceInUseError("La cotización ya tiene un adelanto pendiente o en revisión")
        payment = Payment(
            quote_id=dto.quote_id,
            concept=PaymentConcept.ADVANCE,
            payment_method=dto.payment_method,
            amount=Money(dto.amount),
            evidence_path=dto.evidence_path,
            transaction_reference=dto.transaction_reference,
        )
        await self._payments.save(payment)
        return PaymentCreatedDTO(
            payment_id=payment.id,
            concept=payment.concept,
            validation_status=payment.validation_status,
            message="Comprobante recibido con éxito. En cola de validación.",
        )
