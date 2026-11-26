"""US-12: verificar, rechazar o marcar revisión manual del adelanto."""

from datetime import UTC, datetime

from app.application.dtos.payment_dto import VerifyPaymentDTO, VerifyPaymentInput
from app.application.ports.output.contract_port import IContractIssuer
from app.application.ports.output.payment_repository_port import IPaymentRepositoryPort
from app.application.ports.output.quote_event_port import IQuoteEventProvisioner
from app.domain.entities.payment import PaymentConcept, PaymentValidationStatus
from app.domain.exceptions.payment_exceptions import InvalidPaymentStateError
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError, ValidationError


class VerifyPaymentUseCase:
    def __init__(
        self,
        payments: IPaymentRepositoryPort,
        contracts: IContractIssuer | None = None,
        events: IQuoteEventProvisioner | None = None,
    ) -> None:
        self._payments = payments
        self._contracts = contracts
        self._events = events

    async def execute(self, dto: VerifyPaymentInput) -> VerifyPaymentDTO:
        payment = await self._payments.get_by_id(dto.payment_id)
        if payment is None:
            raise ResourceNotFoundError("Pago no encontrado")
        action = dto.action.upper()
        if action == "VERIFIED":
            event_id = dto.event_id
            if self._contracts is not None:
                events = self._events
                if (
                    event_id is None
                    and events is not None
                    and payment.concept is PaymentConcept.ADVANCE
                ):
                    if (
                        payment.validation_status
                        is not PaymentValidationStatus.PENDING_VERIFICATION
                    ):
                        raise InvalidPaymentStateError(
                            "El adelanto no está pendiente de verificación."
                        )
                    event_id = await events.ensure_event(payment.quote_id)
                    if event_id is None:
                        # RN-04: sin cupo el adelanto queda para aprobación manual de sobrecupo.
                        payment.require_manual_approval()
                        await self._payments.save(payment)
                        return VerifyPaymentDTO(
                            payment_id=payment.id,
                            validation_status=payment.validation_status,
                            rejection_reason=None,
                            event_id=None,
                        )
                if event_id is None:
                    raise ValidationError("event_id es obligatorio para emitir el contrato")
                await self._contracts.prepare_payment_event(event_id, payment.quote_id)
            payment.verify(
                verified_by_user_id=dto.verified_by_user_id,
                event_id=event_id,
                verified_at=datetime.now(UTC),
            )
        elif action == "REJECTED":
            if not dto.rejection_reason or not dto.rejection_reason.strip():
                raise ValidationError("rejection_reason es obligatorio al rechazar")
            payment.reject(reason=dto.rejection_reason, rejected_at=datetime.now(UTC))
        else:
            raise ValidationError("action debe ser VERIFIED o REJECTED")
        await self._payments.save(payment)
        if action == "VERIFIED" and self._contracts is not None and payment.event_id is not None:
            await self._contracts.issue_for_event(payment.event_id, dto.verified_by_user_id)
        return VerifyPaymentDTO(
            payment_id=payment.id,
            validation_status=payment.validation_status,
            rejection_reason=payment.rejection_reason,
            event_id=payment.event_id,
        )
