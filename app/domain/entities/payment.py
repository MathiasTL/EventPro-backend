"""Entidad del dominio de pagos (E5).

Modelo puro de Python sin dependencias de framework ni de persistencia. Centraliza
la máquina de estados de ``validation_status`` y ``audit_status`` según la tabla
``payments`` (diccionario de datos 2.15) y las reglas RN-06/RN-07/RN-09.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain.exceptions.resource_exceptions import (
    InvalidPaymentStateError,
    ValidationError,
)
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


class ValidationStatus(StrEnum):
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    REQUIRES_MANUAL_APPROVAL = "REQUIRES_MANUAL_APPROVAL"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    REFUND_PENDING = "REFUND_PENDING"
    REFUNDED = "REFUNDED"


class AuditStatus(StrEnum):
    UNREVIEWED = "UNREVIEWED"
    REVIEWED = "REVIEWED"
    FLAGGED = "FLAGGED"


_AUDITABLE_TRANSITIONS: dict[AuditStatus | None, set[AuditStatus]] = {
    AuditStatus.UNREVIEWED: {AuditStatus.REVIEWED, AuditStatus.FLAGGED},
    AuditStatus.FLAGGED: {AuditStatus.REVIEWED},
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


@dataclass
class Payment:
    """Pago asociado a una cotización (adelanto) o a un evento (saldo/extensión)."""

    quote_id: UUID
    concept: PaymentConcept
    payment_method: PaymentMethod
    amount: Money
    evidence_path: str
    event_id: UUID | None = None
    transaction_reference: str | None = None
    validation_status: ValidationStatus = ValidationStatus.PENDING_VERIFICATION
    rejection_reason: str | None = None
    verified_by_user_id: UUID | None = None
    verified_at: datetime | None = None
    registered_by_user_id: UUID | None = None
    audit_status: AuditStatus | None = None
    audited_by_user_id: UUID | None = None
    audited_at: datetime | None = None
    audit_notes: str | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        _require(self.amount.amount > 0, "amount debe ser mayor que cero")
        _require(bool(self.evidence_path.strip()), "evidence_path no puede estar vacío")
        if self.concept == PaymentConcept.ADVANCE:
            _require(
                self.audit_status is None,
                "Los pagos ADVANCE no llevan auditoría posterior",
            )
            _require(
                self.event_id is None or self.validation_status == ValidationStatus.VERIFIED,
                "event_id solo se asigna al verificar un ADVANCE",
            )
        else:
            _require(
                self.validation_status == ValidationStatus.VERIFIED,
                "BALANCE y EXTENSION nacen en VERIFIED",
            )
            _require(
                self.audit_status is not None,
                "BALANCE y EXTENSION requieren audit_status",
            )
            _require(
                self.registered_by_user_id is not None and self.event_id is not None,
                "BALANCE y EXTENSION requieren registered_by_user_id y event_id",
            )

    # ---------------- Máquina de estados de validation_status ----------------

    def require_manual_approval(self, reason: str) -> None:
        """Cupo lleno o umbral excedido en la revalidación temprana (RN-09)."""

        if self.validation_status != ValidationStatus.PENDING_VERIFICATION:
            raise InvalidPaymentStateError(
                f"No se puede marcar REQUIRES_MANUAL_APPROVAL desde {self.validation_status}"
            )
        _require(bool(reason.strip()), "reason no puede estar vacío")
        self.validation_status = ValidationStatus.REQUIRES_MANUAL_APPROVAL

    def verify(self, *, verified_by: UUID, event_id: UUID | None = None) -> None:
        """Aprueba el comprobante de un ADVANCE tras la revalidación autoritativa."""

        if self.concept != PaymentConcept.ADVANCE:
            raise InvalidPaymentStateError("Solo los pagos ADVANCE usan verify()")
        if self.validation_status != ValidationStatus.PENDING_VERIFICATION:
            raise InvalidPaymentStateError(
                f"No se puede verificar un pago en {self.validation_status}"
            )
        self.validation_status = ValidationStatus.VERIFIED
        self.verified_by_user_id = verified_by
        self.verified_at = datetime.now(UTC)
        self.event_id = event_id
        self.rejection_reason = None

    def reject(self, *, reason: str) -> None:
        """Rechaza el comprobante; habilita reintento con un nuevo pago."""

        if self.validation_status not in (
            ValidationStatus.PENDING_VERIFICATION,
            ValidationStatus.REQUIRES_MANUAL_APPROVAL,
        ):
            raise InvalidPaymentStateError(
                f"No se puede rechazar un pago en {self.validation_status}"
            )
        _require(bool(reason.strip()), "rejection_reason es obligatorio")
        self.validation_status = ValidationStatus.REJECTED
        self.rejection_reason = reason

    def mark_refund_pending(self) -> None:
        """El encargado decide no aprobar el sobrecupo: se devolverá el adelanto."""

        if self.validation_status != ValidationStatus.REQUIRES_MANUAL_APPROVAL:
            raise InvalidPaymentStateError(
                f"No se puede pasar a REFUND_PENDING desde {self.validation_status}"
            )
        self.validation_status = ValidationStatus.REFUND_PENDING

    def confirm_refund(self) -> None:
        if self.validation_status != ValidationStatus.REFUND_PENDING:
            raise InvalidPaymentStateError(
                f"No se puede confirmar devolución desde {self.validation_status}"
            )
        self.validation_status = ValidationStatus.REFUNDED

    # ---------------- Auditoría posterior (BALANCE / EXTENSION) ----------------

    def audit(
        self,
        *,
        status: AuditStatus,
        audited_by: UUID,
        notes: str | None = None,
    ) -> None:
        if self.concept == PaymentConcept.ADVANCE:
            raise InvalidPaymentStateError("Los pagos ADVANCE no se auditan")
        allowed = _AUDITABLE_TRANSITIONS.get(self.audit_status, set())
        if status not in allowed:
            raise InvalidPaymentStateError(
                f"Transición de auditoría no permitida: {self.audit_status} → {status}"
            )
        if status == AuditStatus.FLAGGED:
            _require(bool(notes and notes.strip()), "audit_notes es obligatorio al marcar FLAGGED")
        self.audit_status = status
        self.audited_by_user_id = audited_by
        self.audited_at = datetime.now(UTC)
        self.audit_notes = notes
