"""Tomar, devolver y reasignar una conversación (spec 09, 6.3, 6.5 y 6.6).

La concurrencia se resuelve con *compare-and-set* sobre ``conversation_links`` y compensación
(D11): cada tramo de base de datos es una transacción corta que confirma antes de llamar a
Chatwoot, de modo que ninguna transacción queda abierta durante la llamada HTTP.
"""

from dataclasses import replace
from uuid import UUID

from app.application.dtos.inbox_dto import ConversationView
from app.application.dtos.messaging_dto import (
    ConversationLifecycle,
    ConversationStatus,
    ConversationSummary,
)
from app.application.ports.output.clock_port import IClockPort
from app.application.ports.output.conversation_event_publisher_port import (
    IConversationEventPublisherPort,
)
from app.application.ports.output.conversation_link_unit_of_work_port import (
    ConversationLinkUnitOfWork,
)
from app.application.ports.output.conversation_session_port import IConversationSessionPort
from app.application.ports.output.messaging_port import IMessagingPort
from app.application.services.audit_service import AuditService
from app.application.use_cases.messaging.conversation_events import conversation_view_event
from app.application.use_cases.messaging.conversation_views import ConversationViewBuilder
from app.core.logging import get_logger
from app.domain.entities.conversation_link import ConversationLink, HandoffReason
from app.domain.exceptions.messaging_exceptions import (
    ConversationNotTakenError,
    ConversationTakenByOtherError,
)
from app.domain.value_objects.role import Role

OVERRIDE_ACTION = "OVERRIDE_CONVERSATION_ASSIGNMENT"
_ENTITY_NAME = "conversation_link"


class _AssignmentFlow:
    """Piezas comunes: vista, aviso a la bandeja y auditoría de intervención."""

    def __init__(
        self,
        messaging: IMessagingPort,
        links: ConversationLinkUnitOfWork,
        views: ConversationViewBuilder,
        sessions: IConversationSessionPort,
        audit: AuditService,
        publisher: IConversationEventPublisherPort,
        clock: IClockPort,
    ) -> None:
        self._messaging = messaging
        self._links = links
        self._views = views
        self._sessions = sessions
        self._audit = audit
        self._publisher = publisher
        self._clock = clock

    async def _view(self, summary: ConversationSummary) -> ConversationView:
        (view,) = await self._views.build([summary])
        return view

    async def _publish(self, view: ConversationView) -> None:
        """Publicar ``conversation.updated`` nunca falla el comando."""

        try:
            await self._publisher.publish(conversation_view_event(view))
        except Exception as exc:
            get_logger("conversation_assignment").warning(
                "conversation_assignment_publish_failed",
                conversation_id=view.chatwoot_conversation_id,
                error_type=type(exc).__name__,
            )

    async def _audit_override(
        self, link: ConversationLink, actor: UUID, old: UUID, new: UUID | None
    ) -> None:
        """D9: solo la intervención de un ``SUPERADMIN`` sobre la asignación de otro."""

        await self._audit.record(
            action=OVERRIDE_ACTION,
            entity_name=_ENTITY_NAME,
            entity_id=link.id,
            user_id=actor,
            old_values={"assigned_user_id": str(old)},
            new_values={"assigned_user_id": str(new) if new else None},
        )


class TakeoverConversation(_AssignmentFlow):
    """Tomar (6.3) y, para un ``SUPERADMIN`` sobre la conversación de otro, reasignar (6.6)."""

    async def execute(self, conversation_id: int, *, user_id: UUID, role: Role) -> ConversationView:
        """Lanza ``ResourceNotFoundError``, ``MessagingUnavailableError`` o
        ``ConversationTakenByOtherError`` (con el asignado vigente).

        Idempotente si ya está ``open`` y asignada al mismo usuario: no escribe ni publica. Si
        Chatwoot falla al reabrir, compensa la asignación antes de relanzar el error.
        """

        summary = await self._messaging.get_conversation(conversation_id)
        was_open = summary.lifecycle is ConversationLifecycle.OPEN
        async with self._links() as links:
            link = await links.ensure(conversation_id, None, self._clock.utcnow())
            # Se compara con el asignado guardado, no con el efectivo (4.1): con Chatwoot aún en
            # ``pending`` una toma de otro encargado puede estar en curso, y tratar el vínculo
            # como libre la pisaría. Un resto de otro usuario lo libera un ``SUPERADMIN``.
            holder = link.assigned_user_id
            if holder == user_id and was_open:
                return await self._view(summary)
            if holder not in (None, user_id) and role is not Role.SUPERADMIN:
                raise ConversationTakenByOtherError(holder)
            if not await links.claim(conversation_id, user_id, holder):
                latest = await links.get(conversation_id)
                raise ConversationTakenByOtherError(latest.assigned_user_id if latest else None)
        # Siempre se reabre (idempotente): la lectura ``open`` pudo quedar vieja si una devolución
        # estaba por aplicar ``pending``. El modo previo sale de esa misma lectura.
        await self._reopen(conversation_id, user_id)
        if not was_open:
            await self._register_manual_handoff(conversation_id)
            await self._clear_bot_session(conversation_id)
        if holder is not None and holder != user_id:
            await self._audit_override(link, user_id, holder, user_id)
        view = await self._view(
            replace(summary, lifecycle=ConversationLifecycle.OPEN, status=ConversationStatus.HUMAN)
        )
        await self._publish(view)
        return view

    async def _reopen(self, conversation_id: int, user_id: UUID) -> None:
        try:
            await self._messaging.set_conversation_status(conversation_id, ConversationStatus.HUMAN)
        except Exception:
            async with self._links() as links:
                await links.release(conversation_id, user_id)
            raise

    async def _register_manual_handoff(self, conversation_id: int) -> None:
        async with self._links() as links:
            link = await links.get(conversation_id)
            if link is not None:
                now = self._clock.utcnow()
                link.register_handoff(reason=HandoffReason.MANUAL_TAKEOVER, summary=None, at=now)
                await links.save(link)

    async def _clear_bot_session(self, conversation_id: int) -> None:
        """D23, de mejor esfuerzo: una falla se registra y no revierte la toma."""

        try:
            await self._sessions.clear(conversation_id)
        except Exception as exc:
            get_logger("conversation_assignment").warning(
                "conversation_bot_session_clear_failed",
                conversation_id=conversation_id,
                error_type=type(exc).__name__,
            )


class ReleaseConversation(_AssignmentFlow):
    """Devolver al bot (6.5): el asignado o un ``SUPERADMIN``."""

    async def execute(self, conversation_id: int, *, user_id: UUID, role: Role) -> ConversationView:
        """Lanza ``ConversationNotTakenError`` (D18) o ``ConversationTakenByOtherError``.

        Idempotente si ya no está ``open``. Chatwoot se actualiza primero: si falla, no cambia nada.
        """

        summary = await self._messaging.get_conversation(conversation_id)
        if summary.lifecycle is not ConversationLifecycle.OPEN:
            return await self._view(summary)
        link = await self._authorize(conversation_id, user_id, role)
        assignee = link.assigned_user_id if link else None
        # Primero Chatwoot, con la asignación aún vigente: una toma ajena recibe 409 hasta que la
        # devolución termine y, si Chatwoot falla, no hay nada que restituir.
        await self._messaging.set_conversation_status(conversation_id, ConversationStatus.BOT)
        if assignee is not None:
            await self._release_assignment(conversation_id, assignee)
        if link is not None and assignee is not None and assignee != user_id:
            await self._audit_override(link, user_id, assignee, None)
        view = await self._view(
            replace(summary, lifecycle=ConversationLifecycle.PENDING, status=ConversationStatus.BOT)
        )
        await self._publish(view)
        return view

    async def _authorize(
        self, conversation_id: int, user_id: UUID, role: Role
    ) -> ConversationLink | None:
        async with self._links() as links:
            link = await links.get(conversation_id)
        assignee = link.assigned_user_id if link else None
        if assignee is None and role is not Role.SUPERADMIN:
            raise ConversationNotTakenError("Primero hay que tomar la conversación.")
        if assignee is not None and assignee != user_id and role is not Role.SUPERADMIN:
            raise ConversationTakenByOtherError(assignee)
        return link

    async def _release_assignment(self, conversation_id: int, assignee: UUID) -> None:
        """Si el CAS pierde (un ``SUPERADMIN`` reasignó entretanto) se registra y no se revierte."""

        async with self._links() as links:
            released = await links.release(conversation_id, assignee)
        if not released:
            get_logger("conversation_assignment").warning(
                "conversation_release_cas_lost", conversation_id=conversation_id
            )
