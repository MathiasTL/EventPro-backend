"""Arma los ítems de la bandeja con los datos de Chatwoot, el vínculo y las consultas por lote.

Cada consulta por lote se hace una sola vez por página (sin N+1, spec 09, D12).
"""

from collections.abc import Sequence
from uuid import UUID

from app.application.dtos.inbox_dto import ConversationView
from app.application.dtos.messaging_dto import ConversationLifecycle, ConversationSummary
from app.application.ports.output.conversation_link_repository_port import (
    IConversationLinkRepositoryPort,
)
from app.application.ports.output.inbox_lookup_port import IInboxLookupPort
from app.application.use_cases.messaging.conversation_events import SERVICE_WINDOW
from app.application.use_cases.messaging.lead_status import derive_lead_status
from app.domain.entities.conversation_link import ConversationLink


def effective_assignee(
    lifecycle: ConversationLifecycle, link: ConversationLink | None
) -> UUID | None:
    """El asignado solo cuenta con la conversación ``open`` (4.1)."""

    if link is None or lifecycle is not ConversationLifecycle.OPEN:
        return None
    return link.assigned_user_id


class ConversationViewBuilder:
    def __init__(self, links: IConversationLinkRepositoryPort, lookup: IInboxLookupPort) -> None:
        self._links = links
        self._lookup = lookup

    async def build(self, summaries: Sequence[ConversationSummary]) -> list[ConversationView]:
        if not summaries:
            return []
        found = await self._links.get_many([s.conversation_id for s in summaries])
        links = {link.chatwoot_conversation_id: link for link in found}
        client_ids = {link.client_id for link in links.values() if link.client_id}
        quote_ids = {link.quote_id for link in links.values() if link.quote_id}
        user_ids = {
            assignee
            for summary in summaries
            if (
                assignee := effective_assignee(
                    summary.lifecycle, links.get(summary.conversation_id)
                )
            )
        }
        client_names = await self._lookup.client_names(client_ids) if client_ids else {}
        quote_statuses = await self._lookup.quote_statuses(quote_ids) if quote_ids else {}
        user_names = await self._lookup.user_names(user_ids) if user_ids else {}

        views: list[ConversationView] = []
        for summary in summaries:
            link = links.get(summary.conversation_id)
            client_id = link.client_id if link else None
            quote_id = link.quote_id if link else None
            assignee = effective_assignee(summary.lifecycle, link)
            quote_status = quote_statuses.get(quote_id) if quote_id else None
            expires_at = (
                link.last_client_message_at + SERVICE_WINDOW
                if link and link.last_client_message_at
                else None
            )
            views.append(
                ConversationView(
                    chatwoot_conversation_id=summary.conversation_id,
                    client_id=client_id,
                    client_name=(client_names.get(client_id) if client_id else None)
                    or summary.contact_name
                    or summary.phone.value,
                    phone=summary.phone.value,
                    quote_id=quote_id,
                    quote_status=quote_status,
                    lead_status=derive_lead_status(quote_status),
                    lifecycle=summary.lifecycle,
                    mode=summary.status,
                    assigned_user_id=assignee,
                    assigned_user_name=user_names.get(assignee) if assignee else None,
                    unread_count=summary.unread_count,
                    handoff_reason=link.handoff_reason if link else None,
                    handed_off_at=link.handed_off_at if link else None,
                    last_message_preview=summary.last_message_preview,
                    last_message_at=summary.last_message_at,
                    service_window_open=summary.service_window_open,
                    service_window_expires_at=expires_at,
                )
            )
        return views
