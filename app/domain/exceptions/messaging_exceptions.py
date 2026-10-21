"""Errores del puerto de mensajería (gateway de WhatsApp)."""

from uuid import UUID

from app.domain.exceptions.resource_exceptions import DomainError


class ServiceWindowClosedError(DomainError):
    """Fuera de la ventana de 24 h (RN-11) solo se admiten plantillas aprobadas."""

    code = "service-window-closed"


class MessagingUnavailableError(DomainError):
    """El gateway de mensajería no responde; el reintento corresponde a la cola outbox."""

    code = "messaging-unavailable"


class InvalidLeadTransitionError(DomainError):
    """El estado comercial actual no admite la transición pedida (D25)."""

    code = "invalid-lead-transition"


class ConversationTakenByOtherError(DomainError):
    """La conversación está asignada a otro usuario (409, spec 09, sección 10)."""

    code = "conversation-taken-by-other"

    def __init__(self, assigned_user_id: UUID | None) -> None:
        super().__init__("La conversación está asignada a otro encargado.")
        self.assigned_user_id = assigned_user_id


class ConversationNotTakenError(DomainError):
    """La conversación está abierta pero sin asignado: primero hay que tomarla (D18)."""

    code = "conversation-not-taken"
