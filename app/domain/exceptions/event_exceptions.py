"""Errores puros de las transiciones del evento."""

from app.domain.exceptions.resource_exceptions import DomainError, ValidationError


class InvalidEventStateError(DomainError):
    code = "invalid-event-state"


class BalancePendingError(DomainError):
    code = "balance-pending"


class ExtensionPaymentMismatchError(DomainError):
    code = "extension-payment-mismatch"


class InvalidEvidenceError(ValidationError):
    code = "invalid-file"
