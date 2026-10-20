"""Errores del puerto de mensajería (gateway de WhatsApp)."""

from app.domain.exceptions.resource_exceptions import DomainError


class ServiceWindowClosedError(DomainError):
    """Fuera de la ventana de 24 h (RN-11) solo se admiten plantillas aprobadas."""

    code = "service-window-closed"


class MessagingUnavailableError(DomainError):
    """El gateway de mensajería no responde; el reintento corresponde a la cola outbox."""

    code = "messaging-unavailable"
