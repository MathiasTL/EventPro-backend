"""Casos de uso del módulo de pagos (E5, Christian): US-11 y US-12.

Orquestan entidad, repositorio, almacenamiento de evidencias y el puerto de
disponibilidad para la revalidación autoritativa (RN-09).
"""

from __future__ import annotations

from uuid import UUID

from app.application.dtos.availability_dto import AvailabilityRequest
from app.application.dtos.payment_dto import (
    AdvancePaymentCreatedDTO,
    AuditPaymentDTO,
    CreateAdvancePaymentDTO,
    PaymentFilterDTO,
    PaymentPageDTO,
    PaymentReadDTO,
    PaymentVerifiedDTO,
    RefundPaymentDTO,
    VerifyPaymentDTO,
)
from app.application.ports.output.availability_port import IAvailabilityPort
from app.application.ports.output.payment_port import (
    IPaymentEvidenceStorage,
    IPaymentRepository,
)
from app.domain.entities.payment import (
    AuditStatus,
    Payment,
    PaymentConcept,
    ValidationStatus,
)
from app.domain.exceptions.resource_exceptions import (
    ResourceInUseError,
    ResourceNotFoundError,
    ValidationError,
)
from app.domain.value_objects.money import Money


def _to_read_dto(payment: Payment) -> PaymentReadDTO:
    return PaymentReadDTO(
        payment_id=payment.id,
        quote_id=payment.quote_id,
        concept=payment.concept,
        payment_method=payment.payment_method,
        amount=payment.amount.amount,
        validation_status=payment.validation_status,
        event_id=payment.event_id,
        audit_status=payment.audit_status,
        transaction_reference=payment.transaction_reference,
        rejection_reason=payment.rejection_reason,
        verified_by_user_id=payment.verified_by_user_id,
        registered_by_user_id=payment.registered_by_user_id,
        audited_by_user_id=payment.audited_by_user_id,
        audited_at=payment.audited_at,
        audit_notes=payment.audit_notes,
        created_at=payment.created_at,
    )


class RegisterAdvancePaymentUseCase:
    """US-11: registra la captura del adelanto y la deja en PENDING_VERIFICATION."""

    def __init__(
        self, repo: IPaymentRepository, availability: IAvailabilityPort | None = None
    ) -> None:
        self._repo = repo
        self._availability = availability

    async def execute(self, dto: CreateAdvancePaymentDTO) -> AdvancePaymentCreatedDTO:
        existing = await self._repo.find_active_advance(dto.quote_id)
        if existing is not None and existing.validation_status in (
            ValidationStatus.PENDING_VERIFICATION,
            ValidationStatus.REQUIRES_MANUAL_APPROVAL,
        ):
            raise ResourceInUseError("La cotización ya tiene un adelanto en verificación")

        payment = Payment(
            quote_id=dto.quote_id,
            concept=PaymentConcept.ADVANCE,
            payment_method=dto.payment_method,
            amount=Money(dto.amount),
            evidence_path=dto.evidence_path,
            transaction_reference=dto.transaction_reference,
        )
        validation_status = ValidationStatus.PENDING_VERIFICATION
        message = "Comprobante recibido con éxito. En cola de validación."
        if self._availability is not None:
            # Revalidación temprana: sin cupo o con umbral superado => aprobación manual.
            result = await self._availability.check_availability(
                AvailabilityRequest(
                    event_date=payment.created_at.date(),
                    start_time=payment.created_at.time(),
                    duration_minutes=60,
                    package_id=dto.quote_id,
                )
            )
            if result.requires_manual_approval:
                payment.require_manual_approval("THRESHOLD_EXCEEDED")
                validation_status = ValidationStatus.REQUIRES_MANUAL_APPROVAL
                message = "Comprobante recibido. El encargado revisará el sobrecupo."
            elif not result.is_available:
                payment.require_manual_approval("CONFLICT")
                validation_status = ValidationStatus.REQUIRES_MANUAL_APPROVAL
                message = "Comprobante recibido. El encargado revisará el caso."

        await self._repo.save(payment)
        return AdvancePaymentCreatedDTO(
            payment_id=payment.id,
            quote_id=payment.quote_id,
            concept=payment.concept,
            validation_status=validation_status,
            message=message,
        )


class ListPaymentsUseCase:
    def __init__(self, repo: IPaymentRepository) -> None:
        self._repo = repo

    async def execute(self, filters: PaymentFilterDTO) -> PaymentPageDTO:
        items = await self._repo.list(filters)
        total = await self._repo.count(filters)
        return PaymentPageDTO(
            items=tuple(items), page=filters.page, page_size=filters.page_size, total=total
        )


class GetPaymentUseCase:
    def __init__(self, repo: IPaymentRepository) -> None:
        self._repo = repo

    async def execute(self, payment_id: UUID) -> PaymentReadDTO:
        payment = await self._repo.get(payment_id)
        if payment is None:
            raise ResourceNotFoundError("Pago no encontrado")
        return _to_read_dto(payment)


class GetPaymentEvidenceUseCase:
    def __init__(self, repo: IPaymentRepository, storage: IPaymentEvidenceStorage) -> None:
        self._repo = repo
        self._storage = storage

    async def execute(self, payment_id: UUID) -> bytes:
        payment = await self._repo.get(payment_id)
        if payment is None:
            raise ResourceNotFoundError("Pago no encontrado")
        return await self._storage.open(payment.evidence_path)


class VerifyPaymentUseCase:
    """US-12: aprueba o rechaza el comprobante de un adelanto."""

    def __init__(self, repo: IPaymentRepository) -> None:
        self._repo = repo

    async def execute(
        self,
        payment_id: UUID,
        dto: VerifyPaymentDTO,
        *,
        verified_by: UUID,
        event_id: UUID | None = None,
    ) -> PaymentVerifiedDTO:
        payment = await self._repo.get(payment_id)
        if payment is None:
            raise ResourceNotFoundError("Pago no encontrado")

        if payment.concept != PaymentConcept.ADVANCE:
            raise ValidationError("Solo los pagos ADVANCE se verifican con este caso de uso")

        if dto.status == ValidationStatus.VERIFIED:
            if payment.validation_status == ValidationStatus.REQUIRES_MANUAL_APPROVAL:
                # La aprobación de un pago en sobrecupo la hace el override (Brenis).
                raise ValidationError("El sobrecupo se aprueba con /overrides/payments")
            payment.verify(verified_by=verified_by, event_id=event_id)
        elif dto.status == ValidationStatus.REJECTED:
            if not dto.rejection_reason or not dto.rejection_reason.strip():
                raise ValidationError("rejection_reason es obligatorio al rechazar")
            payment.reject(reason=dto.rejection_reason)
        else:
            raise ValidationError("status debe ser VERIFIED o REJECTED")

        await self._repo.save(payment)
        return PaymentVerifiedDTO(
            payment_id=payment.id,
            validation_status=payment.validation_status,
        )


class AuditPaymentUseCase:
    def __init__(self, repo: IPaymentRepository) -> None:
        self._repo = repo

    async def execute(
        self, payment_id: UUID, dto: AuditPaymentDTO, *, audited_by: UUID
    ) -> PaymentReadDTO:
        payment = await self._repo.get(payment_id)
        if payment is None:
            raise ResourceNotFoundError("Pago no encontrado")
        if dto.audit_status not in (AuditStatus.REVIEWED, AuditStatus.FLAGGED):
            raise ValidationError("audit_status debe ser REVIEWED o FLAGGED")
        payment.audit(status=dto.audit_status, audited_by=audited_by, notes=dto.audit_notes)
        await self._repo.save(payment)
        return _to_read_dto(payment)


class RefundPaymentUseCase:
    def __init__(self, repo: IPaymentRepository) -> None:
        self._repo = repo

    async def execute(self, payment_id: UUID, dto: RefundPaymentDTO) -> PaymentReadDTO:
        payment = await self._repo.get(payment_id)
        if payment is None:
            raise ResourceNotFoundError("Pago no encontrado")
        payment.confirm_refund()
        await self._repo.save(payment)
        return _to_read_dto(payment)
