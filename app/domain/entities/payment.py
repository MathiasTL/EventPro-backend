"""Agregado Payment: adelanto, saldo pre-show y extensiones en vivo (E5, US-11/US-12)."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain.exceptions.payment_exceptions import InvalidPaymentStateError
from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.money import Money


class PaymentConcept(StrEnum):
    ADVANCE = "ADVANCE"
    BALANCE = "BALANCE"
    EXTENSION = "EXTENSION"


class PaymentMethod(StrEnum):
    YAPE = "YAPE"
    PLIN = "PLIN"
    BANK_TRANSFER = "BANK_TRANSFER"
    CASH = "CASH"


class PaymentValidationStatus(StrEnum):
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    REQUIRES_MANUAL_APPROVAL = "REQUIRES_MANUAL_APPROVAL"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    REFUND_PENDING = "REFUND_PENDING"
    REFUNDED = "REFUNDED"


class PaymentAuditStatus(StrEnum):
    UNREVIEWED = "UNREVIEWED"
    REVIEWED = "REVIEWED"
    FLAGGED = "FLAGGED"


@dataclass(kw_only=True)
class Payment:
    quote_id: UUID
    concept: PaymentConcept
    payment_method: PaymentMethod
    amount: Money
    evidence_path: str
    validation_status: PaymentValidationStatus = PaymentValidationStatus.PENDING_VERIFICATION
    audit_status: PaymentAuditStatus | None = None
    event_id: UUID | None = None
    transaction_reference: str | None = None
    rejection_reason: str | None = None
    verified_by_user_id: UUID | None = None
    verified_at: datetime | None = None
    registered_by_user_id: UUID | None = None
    audited_by_user_id: UUID | None = None
    audited_at: datetime | None = None
    audit_notes: str | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Money) or self.amount.amount <= Decimal("0"):
            raise ValidationError("amount debe ser un importe PEN mayor que cero")
        if self.amount.currency != "PEN":
            raise ValidationError("amount debe ser PEN")
        if not isinstance(self.evidence_path, str) or not self.evidence_path.strip():
            raise ValidationError("evidence_path debe ser una ruta no vacía")
        if not isinstance(self.quote_id, UUID):
            raise ValidationError("quote_id debe ser UUID")
        if self.concept is PaymentConcept.ADVANCE:
            if self.audit_status is not None:
                raise ValidationError("ADVANCE no usa audit_status")
            if self.registered_by_user_id is not None:
                raise ValidationError("ADVANCE no requiere registered_by_user_id")
            if self.event_id is not None and self.validation_status not in (
                PaymentValidationStatus.VERIFIED,
                PaymentValidationStatus.REFUND_PENDING,
                PaymentValidationStatus.REFUNDED,
            ):
                raise ValidationError("ADVANCE solo puede tener event_id una vez resuelto")
            if (
                self.validation_status
                in (
                    PaymentValidationStatus.VERIFIED,
                    PaymentValidationStatus.REFUNDED,
                )
                and self.verified_by_user_id is None
            ):
                raise ValidationError("El estado VERIFIED/REFUNDED exige verified_by_user_id")
        else:
            if self.validation_status is not PaymentValidationStatus.VERIFIED:
                raise ValidationError("BALANCE y EXTENSION nacen sujetas a pre-show verificado")
            if self.event_id is None or self.registered_by_user_id is None:
                raise ValidationError(
                    "BALANCE y EXTENSION requieren event_id y registered_by_user_id"
                )
            if self.audit_status is None:
                raise ValidationError("BALANCE y EXTENSION requieren audit_status inicial")
            if self.verified_by_user_id is not None or self.verified_at is not None:
                raise ValidationError("BALANCE y EXTENSION no llevan verified_by_user_id")
            if (
                self.transaction_reference is not None
                and not str(self.transaction_reference).strip()
            ):
                raise ValidationError("transaction_reference no puede estar vacío")
        if (
            self.audit_status is not None
            and self.audited_at is None
            and self.audit_status in (PaymentAuditStatus.REVIEWED, PaymentAuditStatus.FLAGGED)
        ):
            raise ValidationError("audit_status exige audited_at")
        if self.audited_at is not None and self.audited_at.tzinfo is None:
            raise ValidationError("audited_at debe tener zona horaria")

    def verify(
        self, *, verified_by_user_id: UUID, event_id: UUID | None, verified_at: datetime
    ) -> None:
        if self.concept is not PaymentConcept.ADVANCE:
            raise InvalidPaymentStateError("Solo ADVANCE admite verificación de comprobante.")
        if self.validation_status is not PaymentValidationStatus.PENDING_VERIFICATION:
            raise InvalidPaymentStateError("El adelanto no está pendiente de verificación.")
        if verified_at.tzinfo is None or verified_at.utcoffset() is None:
            raise ValidationError("verified_at debe incluir zona horaria")
        self.validation_status = PaymentValidationStatus.VERIFIED
        self.verified_by_user_id = verified_by_user_id
        self.verified_at = verified_at.astimezone(UTC)
        self.event_id = event_id
        self.rejection_reason = None

    def approve_overbooked(
        self, *, verified_by_user_id: UUID, event_id: UUID | None, approved_at: datetime
    ) -> None:
        """Aprobación manual del sobrecupo (RN-04, RF-20): REQUIRES_MANUAL_APPROVAL -> VERIFIED."""

        if self.concept is not PaymentConcept.ADVANCE:
            raise InvalidPaymentStateError("Solo ADVANCE admite aprobación de sobrecupo.")
        if self.validation_status is not PaymentValidationStatus.REQUIRES_MANUAL_APPROVAL:
            raise InvalidPaymentStateError("El pago no requiere aprobación manual.")
        if approved_at.tzinfo is None or approved_at.utcoffset() is None:
            raise ValidationError("approved_at debe incluir zona horaria")
        self.validation_status = PaymentValidationStatus.VERIFIED
        self.verified_by_user_id = verified_by_user_id
        self.verified_at = approved_at.astimezone(UTC)
        self.event_id = event_id
        self.rejection_reason = None

    def reject(self, *, reason: str, rejected_at: datetime) -> None:
        if self.concept is not PaymentConcept.ADVANCE:
            raise InvalidPaymentStateError("Solo se pueden rechazar captura de adelanto.")
        if self.validation_status not in (
            PaymentValidationStatus.PENDING_VERIFICATION,
            PaymentValidationStatus.REQUIRES_MANUAL_APPROVAL,
        ):
            raise InvalidPaymentStateError("El adelanto no está en estado susceptible de rechazo.")
        if not reason.strip():
            raise ValidationError("El motivo de rechazo es obligatorio")
        self.validation_status = PaymentValidationStatus.REJECTED
        self.rejection_reason = reason.strip()
        self.verified_at = rejected_at.astimezone(UTC)
        self.verified_by_user_id = self.verified_by_user_id

    def mark_refund_pending(self) -> None:
        if self.validation_status != PaymentValidationStatus.REQUIRES_MANUAL_APPROVAL:
            raise InvalidPaymentStateError("Solo se pueden reembolsar adelantos en sobrecupo.")
        self.validation_status = PaymentValidationStatus.REFUND_PENDING

    def confirm_refund(self) -> None:
        if self.validation_status != PaymentValidationStatus.REFUND_PENDING:
            raise InvalidPaymentStateError("Solo se pueden confirmar reembolsos pendientes.")
        self.validation_status = PaymentValidationStatus.REFUNDED

    def audit(
        self,
        *,
        audited_by_user_id: UUID,
        status: PaymentAuditStatus,
        notes: str | None,
    ) -> None:
        if self.concept is PaymentConcept.ADVANCE:
            raise InvalidPaymentStateError("Los adelantos no tienen auditoría posterior.")
        if self.audit_status is None:
            raise InvalidPaymentStateError("Este pago no tiene audit_status.")
        if self.audit_status is PaymentAuditStatus.REVIEWED:
            raise InvalidPaymentStateError("El cobro ya fue revisado.")
        if status is PaymentAuditStatus.FLAGGED and not (notes and notes.strip()):
            raise ValidationError("audit_notes es obligatorio al marcar FLAGGED")
        if (
            self.audit_status is PaymentAuditStatus.FLAGGED
            and status is PaymentAuditStatus.UNREVIEWED
        ):
            raise InvalidPaymentStateError("Una auditoría marcada no puede volver a UNREVIEWED.")
        self.audit_status = status
        self.audited_by_user_id = audited_by_user_id
        self.audited_at = datetime.now(UTC)
        self.audit_notes = notes.strip() if notes else None
