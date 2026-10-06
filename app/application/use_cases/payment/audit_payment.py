"""US-12/PC-12: auditoría posterior de cobros BALANCE o EXTENSION."""

from app.application.dtos.payment_dto import AuditPaymentDTO, AuditPaymentInput
from app.application.ports.output.payment_repository_port import IPaymentRepositoryPort
from app.application.services.audit_service import AuditService
from app.domain.entities.payment import PaymentAuditStatus
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError, ValidationError


class AuditPaymentUseCase:
    def __init__(self, payments: IPaymentRepositoryPort, audits: AuditService) -> None:
        self._payments = payments
        self._audits = audits

    async def execute(self, dto: AuditPaymentInput) -> AuditPaymentDTO:
        payment = await self._payments.get_by_id(dto.payment_id)
        if payment is None:
            raise ResourceNotFoundError("Pago no encontrado")
        if dto.audit_status not in (PaymentAuditStatus.REVIEWED, PaymentAuditStatus.FLAGGED):
            raise ValidationError("audit_status debe ser REVIEWED o FLAGGED")
        old = payment.audit_status.value if payment.audit_status else None
        payment.audit(
            audited_by_user_id=dto.audited_by_user_id,
            status=dto.audit_status,
            notes=dto.audit_notes,
        )
        assert payment.audit_status is not None
        await self._payments.save(payment)
        await self._audits.record(
            action="AUDIT_PAYMENT",
            entity_name="payments",
            entity_id=payment.id,
            user_id=dto.audited_by_user_id,
            old_values={"audit_status": old},
            new_values={
                "audit_status": payment.audit_status.value,
                "audit_notes": payment.audit_notes,
            },
        )
        assert payment.audited_at is not None
        return AuditPaymentDTO(
            payment_id=payment.id,
            audit_status=payment.audit_status,
            audited_at=payment.audited_at,
        )
