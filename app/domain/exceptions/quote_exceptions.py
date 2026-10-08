"""Errores de negocio del núcleo de cotización (E1)."""

from app.domain.exceptions.resource_exceptions import DomainError


class InvalidQuoteStateError(DomainError):
    """La transición solicitada no es válida desde el estado actual de la cotización."""

    code = "invalid-quote-state"


class QuoteExpiredError(DomainError):
    """La cotización venció y ya no admite iniciar el pago."""

    code = "quote-expired"


class RouteEstimationError(DomainError):
    """El estimador de rutas no pudo calcular distancia y duración.

    No sale del caso de uso: activa la contingencia por zona (escenario C).
    """

    code = "route-estimation-failed"
