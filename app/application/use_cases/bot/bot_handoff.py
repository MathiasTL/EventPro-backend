"""Vínculo de la conversación con el bot: cotización creada y derivación persistente (spec 09, 6.2).

``link_created_quote`` corre dentro de la transacción del bot, de modo que el vínculo se confirma
con la cotización. ``BotHandoffRecorder`` corre solo después de que Chatwoot dejó la conversación
en manos de un encargado: guarda motivo, resumen e instante, limpia una asignación vieja y avisa
a la bandeja. Todo es de mejor esfuerzo: una falla se registra y nunca rompe la respuesta del bot.

El resumen sale solo de campos estructurados de la sesión (catálogo, fecha, distrito, cotización);
jamás del texto libre del cliente, su nombre ni su dirección.
"""

from dataclasses import replace
from datetime import date, datetime
from typing import Any

from app.application.dtos.inbox_dto import ConversationView
from app.application.dtos.messaging_dto import ConversationLifecycle, ConversationStatus
from app.application.dtos.quote_dto import CreatedQuoteDTO
from app.application.ports.output.bot_unit_of_work_port import BotTransaction
from app.application.ports.output.clock_port import IClockPort
from app.application.ports.output.conversation_event_publisher_port import (
    IConversationEventPublisherPort,
)
from app.application.ports.output.conversation_link_unit_of_work_port import (
    ConversationLinkUnitOfWork,
)
from app.application.ports.output.inbox_lookup_port import IInboxLookupPort
from app.application.ports.output.messaging_port import IMessagingPort
from app.application.use_cases.bot import bot_messages as texts
from app.application.use_cases.bot.agent_session import AgentSession
from app.application.use_cases.bot.bot_session import BotSession
from app.application.use_cases.messaging.conversation_events import (
    conversation_view_event,
    handoff_requested_event,
)
from app.application.use_cases.messaging.conversation_views import ConversationViewBuilder
from app.core.logging import get_logger
from app.domain.entities.conversation_link import ConversationLink, HandoffReason
from app.domain.value_objects.phone_number import PhoneNumber

_REASONS = {
    "requested": HandoffReason.CLIENT_REQUEST,
    "chosen": HandoffReason.CLIENT_REQUEST,
    "client_request": HandoffReason.CLIENT_REQUEST,
    "not_understood": HandoffReason.BOT_NOT_UNDERSTOOD,
    "bot_not_understood": HandoffReason.BOT_NOT_UNDERSTOOD,
    "tool_loop_limit": HandoffReason.BOT_NOT_UNDERSTOOD,
    "error": HandoffReason.BOT_ERROR,
    "no_catalog": HandoffReason.BOT_ERROR,
    "llm_after_action": HandoffReason.BOT_ERROR,
}


def map_reason(reason: str) -> HandoffReason:
    """Motivo interno del bot a ``HandoffReason`` (D2); lo desconocido es una falla del bot."""

    return _REASONS.get(reason, HandoffReason.BOT_ERROR)


async def link_created_quote(
    tx: BotTransaction, conversation_id: int, quote: CreatedQuoteDTO, now: datetime
) -> None:
    """Vincula la cotización recién creada (la más reciente gana) en la transacción del bot."""

    links = tx.conversation_links
    link = await links.ensure(conversation_id, quote.client_id, now)
    link.link_client(quote.client_id, at=now)
    link.link_quote(quote.quote_id, at=now)
    await links.save(link)


def quote_details(session: BotSession) -> str:
    """Datos estructurados de la cotización: paquete, temática, fecha y distrito."""

    parts: list[str | None] = [
        session.package_name or texts.CATEGORY_LABELS.get(session.category or ""),
        session.theme_name,
        texts.format_date(date.fromisoformat(session.event_date)) if session.event_date else None,
        session.district,
    ]
    return ", ".join(part for part in parts if part)


def menu_summary(session: BotSession) -> str | None:
    return _summary(session.quote_id, quote_details(session))


def agent_summary(session: AgentSession) -> str | None:
    return _summary(session.quote_id, session.quote_details or "")


def stored_session_summary(stored: dict[str, Any] | None) -> str | None:
    """Resumen de una sesión guardada, sea del motor de menús o del agente."""

    if stored is None:
        return None
    menu = BotSession.from_dict(dict(stored))
    if menu is not None:
        return menu_summary(menu)
    agent = AgentSession.from_dict(stored)
    return agent_summary(agent) if agent is not None else None


def _summary(quote_id: str | None, details: str) -> str | None:
    if quote_id:
        return f"Cotización {quote_id[:8]}: {details}" if details else f"Cotización {quote_id[:8]}"
    return f"Sin cotización: {details}" if details else None


class BotHandoffRecorder:
    def __init__(
        self,
        *,
        links: ConversationLinkUnitOfWork,
        lookup: IInboxLookupPort,
        messaging: IMessagingPort,
        publisher: IConversationEventPublisherPort,
        clock: IClockPort,
    ) -> None:
        self._links = links
        self._lookup = lookup
        self._messaging = messaging
        self._publisher = publisher
        self._clock = clock

    async def record(
        self, conversation_id: int, phone: PhoneNumber, *, reason: str, summary: str | None
    ) -> None:
        """Registra la derivación y avisa a la bandeja; nunca lanza."""

        log = get_logger("bot")
        try:
            link = await self._persist(conversation_id, map_reason(reason), summary)
        except Exception as error:
            log.error(
                "bot_handoff_record_failed",
                conversation_id=conversation_id,
                error_type=type(error).__name__,
            )
            return
        view = await self._view(conversation_id)
        events = [
            handoff_requested_event(
                link=link,
                client_name=view.client_name if view else phone.value,
                phone=view.phone if view else phone.value,
            )
        ]
        if view is not None:
            events.append(conversation_view_event(view))
        for event in events:
            try:
                await self._publisher.publish(event)
            except Exception as error:
                log.warning(
                    "bot_handoff_publish_failed",
                    conversation_id=conversation_id,
                    error_type=type(error).__name__,
                )

    async def _persist(
        self, conversation_id: int, reason: HandoffReason, summary: str | None
    ) -> ConversationLink:
        """Una transacción corta: derivación y limpieza de un asignado viejo (``open`` sin dueño).

        El *compare-and-set* espera el asignado leído aquí mismo; si una toma legítima ganó
        en ese instante, la liberación pierde, se registra y la toma sigue (spec 09, sección 15).
        """

        async with self._links() as links:
            now = self._clock.utcnow()
            link = await links.ensure(conversation_id, None, now)
            holder = link.assigned_user_id
            link.register_handoff(reason=reason, summary=summary, at=now)
            await links.save(link)
            if holder is not None:
                if await links.release(conversation_id, holder):
                    link.unassign(at=now)
                else:
                    get_logger("bot").warning(
                        "bot_handoff_release_cas_lost", conversation_id=conversation_id
                    )
        return link

    async def _view(self, conversation_id: int) -> ConversationView | None:
        try:
            summary = await self._messaging.get_conversation(conversation_id)
            summary = replace(
                summary, lifecycle=ConversationLifecycle.OPEN, status=ConversationStatus.HUMAN
            )
            async with self._links() as links:
                (view,) = await ConversationViewBuilder(links, self._lookup).build([summary])
        except Exception as error:
            get_logger("bot").warning(
                "bot_handoff_view_failed",
                conversation_id=conversation_id,
                error_type=type(error).__name__,
            )
            return None
        return view
