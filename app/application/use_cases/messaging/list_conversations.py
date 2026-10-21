"""Lectura de la bandeja: lista filtrada y una conversación (spec 09, 4.1 y 7.2, D12, D21).

La bandeja se arma en memoria: se leen hasta 500 conversaciones de Chatwoot, se unen con los
vínculos y las consultas por lote, y se filtran, ordenan y paginan aquí.
"""

import unicodedata
from datetime import UTC, datetime
from uuid import UUID

from app.application.dtos.inbox_dto import (
    INBOX_SCAN_LIMIT,
    AssignedFilter,
    ConversationFilters,
    ConversationPage,
    ConversationView,
)
from app.application.dtos.messaging_dto import ConversationLifecycle
from app.application.ports.output.messaging_port import IMessagingPort
from app.application.use_cases.messaging.conversation_views import ConversationViewBuilder

_OLDEST = datetime.min.replace(tzinfo=UTC)


class ListConversations:
    def __init__(self, messaging: IMessagingPort, views: ConversationViewBuilder) -> None:
        self._messaging = messaging
        self._views = views

    async def execute(self, filters: ConversationFilters, *, user_id: UUID) -> ConversationPage:
        """``user_id`` resuelve ``assigned=me``."""

        summaries = await self._messaging.list_conversations(
            include_resolved=filters.include_resolved, page=1, page_size=INBOX_SCAN_LIMIT
        )
        views = await self._views.build(summaries)
        matching = sorted(
            (view for view in views if _matches(view, filters, user_id)),
            key=lambda view: (view.last_message_at or _OLDEST, view.chatwoot_conversation_id),
            reverse=True,
        )
        start = (max(filters.page, 1) - 1) * filters.page_size
        return ConversationPage(
            items=matching[start : start + filters.page_size],
            page=filters.page,
            page_size=filters.page_size,
            total=len(matching),
        )


class GetConversation:
    def __init__(self, messaging: IMessagingPort, views: ConversationViewBuilder) -> None:
        self._messaging = messaging
        self._views = views

    async def execute(self, conversation_id: int) -> ConversationView:
        """Lanza ``ResourceNotFoundError`` si la conversación no existe (incluye ``resolved``)."""

        summary = await self._messaging.get_conversation(conversation_id)
        (view,) = await self._views.build([summary])
        return view


def _matches(view: ConversationView, filters: ConversationFilters, user_id: UUID) -> bool:
    if filters.mode is not None and view.mode is not filters.mode:
        return False
    if filters.assigned is AssignedFilter.ME and view.assigned_user_id != user_id:
        return False
    if filters.assigned is AssignedFilter.UNASSIGNED and not (
        view.lifecycle is ConversationLifecycle.OPEN and view.assigned_user_id is None
    ):
        return False
    if filters.assigned_user_id is not None and view.assigned_user_id != filters.assigned_user_id:
        return False
    return filters.q is None or _matches_search(view, filters.q)


def _matches_search(view: ConversationView, query: str) -> bool:
    """Nombre sin distinguir mayúsculas ni tildes, o dígitos del teléfono (4.1)."""

    needle = _fold(query)
    if needle and needle in _fold(view.client_name):
        return True
    digits = _digits(query)
    return bool(digits) and digits in _digits(view.phone)


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.strip().casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _digits(text: str) -> str:
    return "".join(char for char in text if char.isdigit())
