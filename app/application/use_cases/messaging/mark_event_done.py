"""Marca manual de «Evento realizado» en una conversación (spec 09, 7.4, D25)."""

from dataclasses import replace
from uuid import UUID

from app.application.dtos.inbox_dto import ConversationView, LeadStatus
from app.application.ports.output.clock_port import IClockPort
from app.application.ports.output.conversation_event_publisher_port import (
    IConversationEventPublisherPort,
)
from app.application.ports.output.conversation_link_repository_port import (
    IConversationLinkRepositoryPort,
)
from app.application.ports.output.messaging_port import IMessagingPort
from app.application.use_cases.messaging.conversation_events import conversation_view_event
from app.application.use_cases.messaging.conversation_views import ConversationViewBuilder
from app.core.logging import get_logger
from app.domain.exceptions.messaging_exceptions import InvalidLeadTransitionError


class MarkEventDone:
    """Solo cambia el estado comercial: no toca el estado de Chatwoot, el modo ni la asignación."""

    def __init__(
        self,
        messaging: IMessagingPort,
        links: IConversationLinkRepositoryPort,
        views: ConversationViewBuilder,
        publisher: IConversationEventPublisherPort,
        clock: IClockPort,
    ) -> None:
        self._messaging = messaging
        self._links = links
        self._views = views
        self._publisher = publisher
        self._clock = clock

    async def execute(self, conversation_id: int, *, user_id: UUID) -> ConversationView:
        """Lanza ``ResourceNotFoundError`` o ``MessagingUnavailableError`` si Chatwoot falla.

        Con un estado comercial distinto de ``CONVERTED`` lanza ``InvalidLeadTransitionError``.

        Es idempotente si el estado ya es ``EVENT_DONE`` (calculado o marcado): no escribe ni
        publica. Publicar ``conversation.updated`` nunca falla el comando.
        """

        summary = await self._messaging.get_conversation(conversation_id)
        (view,) = await self._views.build([summary])
        if view.lead_status is LeadStatus.EVENT_DONE:
            return view
        link = await self._links.get(conversation_id)
        if view.lead_status is not LeadStatus.CONVERTED or link is None:
            raise InvalidLeadTransitionError(
                "Solo una conversación con cotización convertida puede marcarse "
                "como evento realizado."
            )
        link.mark_event_done(user_id=user_id, at=self._clock.utcnow())
        await self._links.save(link)
        updated = replace(view, lead_status=LeadStatus.EVENT_DONE)
        try:
            await self._publisher.publish(conversation_view_event(updated))
        except Exception as exc:
            get_logger("conversation_event_done").warning(
                "conversation_event_done_publish_failed",
                conversation_id=conversation_id,
                error_type=type(exc).__name__,
            )
        return updated
