"""Errores de negocio de la cola de mensajes salientes (outbox)."""

from app.domain.exceptions.resource_exceptions import DomainError


class InvalidOutboxStateError(DomainError):
    """La transición solicitada no es válida desde el estado actual del mensaje."""

    code = "invalid-outbox-state"
