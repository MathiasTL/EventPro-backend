"""Estado comercial derivado de una conversación (spec 09, 4.2, D14). Función pura."""

from collections.abc import Mapping
from uuid import UUID

from app.application.dtos.inbox_dto import LeadStatus
from app.application.ports.output.inbox_lookup_port import IInboxLookupPort
from app.domain.entities.conversation_link import ConversationLink
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


async def settled_among_converted(
    lookup: IInboxLookupPort, statuses: Mapping[UUID, QuoteStatus]
) -> set[UUID]:
    """Una sola lectura: de las cotizaciones ``CONVERTED``, las que tienen el evento ``SETTLED``."""

    converted = [
        quote_id for quote_id, status in statuses.items() if status is QuoteStatus.CONVERTED
    ]
    return await lookup.settled_quote_ids(converted) if converted else set()


def link_event_done(link: ConversationLink, settled: set[UUID]) -> bool:
    """Evento ``SETTLED`` o marca manual; solo cuenta con una cotización vinculada."""

    return link.quote_id is not None and (
        link.event_done_at is not None or link.quote_id in settled
    )


async def resolve_lead(
    lookup: IInboxLookupPort, link: ConversationLink
) -> tuple[QuoteStatus | None, LeadStatus]:
    """Estado de la cotización y estado comercial de un solo vínculo (worker y marca manual)."""

    if link.quote_id is None:
        return None, LeadStatus.QUOTING
    statuses = await lookup.quote_statuses([link.quote_id])
    settled = await settled_among_converted(lookup, statuses)
    quote_status = statuses.get(link.quote_id)
    return quote_status, derive_lead_status(quote_status, event_done=link_event_done(link, settled))
