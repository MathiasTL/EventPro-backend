"""Errores de negocio de la cola de mensajes salientes (outbox)."""

from app.domain.exceptions.resource_exceptions import DomainError, ResourceNotFoundError


class InvalidOutboxStateError(DomainError):
    """La transición solicitada no es válida desde el estado actual del mensaje."""

    code = "invalid-outbox-state"


class OutboxMessageNotFoundError(ResourceNotFoundError):
    """La fila del outbox no existe o no pertenece a la conversación indicada."""
