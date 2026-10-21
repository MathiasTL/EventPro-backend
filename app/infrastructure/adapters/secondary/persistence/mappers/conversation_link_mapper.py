"""Conversión explícita entre ConversationLinkModel y el agregado ConversationLink."""

from app.domain.entities.conversation_link import ConversationLink, HandoffReason
from app.infrastructure.adapters.secondary.persistence.models.conversation_link_model import (
    ConversationLinkModel,
)


def conversation_link_to_domain(row: ConversationLinkModel) -> ConversationLink:
    return ConversationLink(
        id=row.id,
        chatwoot_conversation_id=row.chatwoot_conversation_id,
        client_id=row.client_id,
        quote_id=row.quote_id,
        assigned_user_id=row.assigned_user_id,
        handoff_reason=HandoffReason(row.handoff_reason) if row.handoff_reason else None,
        handoff_summary=row.handoff_summary,
        handed_off_at=row.handed_off_at,
        last_client_message_at=row.last_client_message_at,
        event_done_at=row.event_done_at,
        event_done_by_user_id=row.event_done_by_user_id,
        lead_cycle_started_at=row.lead_cycle_started_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def apply_conversation_link_to_model(row: ConversationLinkModel, link: ConversationLink) -> None:
    """Copia el estado mutable salvo ``assigned_user_id``, que solo cambia con claim/release."""

    row.client_id = link.client_id
    row.quote_id = link.quote_id
    row.handoff_reason = link.handoff_reason.value if link.handoff_reason else None
    row.handoff_summary = link.handoff_summary
    row.handed_off_at = link.handed_off_at
    row.last_client_message_at = link.last_client_message_at
    row.event_done_at = link.event_done_at
    row.event_done_by_user_id = link.event_done_by_user_id
    row.lead_cycle_started_at = link.lead_cycle_started_at
    row.updated_at = link.updated_at


def conversation_link_to_model(link: ConversationLink) -> ConversationLinkModel:
    row = ConversationLinkModel(
        id=link.id,
        chatwoot_conversation_id=link.chatwoot_conversation_id,
        assigned_user_id=link.assigned_user_id,
        created_at=link.created_at,
    )
    apply_conversation_link_to_model(row, link)
    return row
