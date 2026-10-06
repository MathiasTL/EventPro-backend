"""Errores puros de las transiciones de Payment."""

from app.domain.exceptions.resource_exceptions import DomainError


class InvalidPaymentStateError(DomainError):
    code = "invalid-payment-state"
