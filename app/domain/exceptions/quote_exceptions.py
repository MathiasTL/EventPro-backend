"""Errores de negocio del núcleo de cotización (E1)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, time

from app.domain.exceptions.resource_exceptions import DomainError, ResourceNotFoundError


class InvalidQuoteStateError(DomainError):
    """La transición solicitada no es válida desde el estado actual de la cotización."""

    code = "invalid-quote-state"


class QuoteExpiredError(DomainError):
    """La cotización venció y ya no admite iniciar el pago."""

    code = "quote-expired"


class PaymentUnderReviewError(DomainError):
    """La cotización venció, pero tiene un pago en verificación que debe resolverse primero."""

    code = "payment-under-review"


class RouteEstimationError(DomainError):
    """El estimador de rutas no pudo calcular distancia y duración.

    No sale del caso de uso: activa la contingencia por zona (escenario C).
    """

    code = "route-estimation-failed"


@dataclass(frozen=True)
class AvailabilityAlternative:
    """Fecha y hora locales alternativas que el bot puede ofrecer al cliente."""

    event_date: date
    event_time: time


class AvailabilityRejectedError(DomainError):
    """No hay disponibilidad para la fecha y el horario pedidos.

    Lleva las alternativas sugeridas y si el cliente puede pedir la ayuda de un encargado.
    """

    code = "availability-rejected"

    def __init__(
        self,
        message: str,
        *,
        alternatives: Sequence[AvailabilityAlternative] = (),
        handoff_available: bool = True,
    ) -> None:
        super().__init__(message)
        self.alternatives: tuple[AvailabilityAlternative, ...] = tuple(alternatives)
        self.handoff_available = handoff_available


class AvailabilityConflictError(AvailabilityRejectedError):
    """El cupo para la fecha y el horario ya está ocupado."""

    code = "availability-conflict"


class SimultaneousThresholdExceededError(AvailabilityRejectedError):
    """Se superaría el máximo de shows simultáneos y se requiere aprobación manual."""

    code = "simultaneous-threshold-exceeded"


class QuoteNotFoundError(ResourceNotFoundError):
    """La cotización solicitada no existe."""

    code = "quote-not-found"


class ClientNotFoundError(ResourceNotFoundError):
    """El cliente solicitado no existe."""

    code = "client-not-found"
