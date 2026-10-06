"""Errores puros de las transiciones del evento."""

from app.domain.exceptions.resource_exceptions import DomainError


class InvalidEventStateError(DomainError):
    code = "invalid-event-state"


class BalancePendingError(DomainError):
    code = "balance-pending"
