"""Estado comercial derivado de una conversación (spec 09, 4.2, D14). Función pura."""

from app.application.dtos.inbox_dto import LeadStatus
from app.domain.entities.quote import QuoteStatus

_BY_QUOTE_STATUS: dict[QuoteStatus, LeadStatus] = {
    QuoteStatus.SENT: LeadStatus.QUOTE_SENT,
    QuoteStatus.PAYMENT_STARTED: LeadStatus.PAYMENT_STARTED,
    QuoteStatus.CONVERTED: LeadStatus.CONVERTED,
    QuoteStatus.EXPIRED: LeadStatus.QUOTE_CLOSED,
    QuoteStatus.CANCELLED: LeadStatus.QUOTE_CLOSED,
}


def derive_lead_status(quote_status: QuoteStatus | None, *, event_done: bool = False) -> LeadStatus:
    """Sin cotización vinculada el bot aún recoge datos (``QUOTING``).

    ``event_done`` es el punto de extensión de D25 (B5b): solo una cotización ``CONVERTED``
    puede pasar a ``EVENT_DONE``, por un evento ``SETTLED`` o por la marca manual.
    """

    if quote_status is None:
        return LeadStatus.QUOTING
    if event_done and quote_status is QuoteStatus.CONVERTED:
        return LeadStatus.EVENT_DONE
    return _BY_QUOTE_STATUS[quote_status]
