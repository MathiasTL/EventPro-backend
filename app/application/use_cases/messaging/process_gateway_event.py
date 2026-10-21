"""Caso de uso ProcessGatewayEvent: punto de enrutamiento de los eventos del gateway.

Los avisos de entrega cambian el outbox y los mensajes (entrantes y ecos salientes) mantienen
el vínculo de la conversación; ambos publican su evento para la bandeja (spec 09, 6.1). Lo
demás se registra y se da por recibido. Los logs llevan identificadores y estados, nunca
contenido de mensajes, nombres ni teléfonos.
"""

from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from typing import Protocol

from app.application.dtos.conversation_event_dto import ConversationEvent
from app.application.dtos.gateway_event_dto import (
    ConversationSnapshot,
    DeliveryNotice,
    GatewayEventOutcome,
    IncomingClientMessage,
    MessageDetails,
    OutgoingMessageEcho,
    UnhandledGatewayEvent,
)
from app.application.dtos.messaging_dto import (
    ConversationLifecycle,
    ConversationStatus,
    MessageDirection,
)
from app.application.ports.output.conversation_event_publisher_port import (
    IConversationEventPublisherPort,
)
from app.application.ports.output.gateway_event_port import IGatewayEventPort
from app.application.ports.output.inbox_event_unit_of_work_port import (
    InboxEventTransaction,
    InboxEventUnitOfWork,
)
from app.application.ports.output.inbox_lookup_port import IInboxLookupPort
from app.application.ports.output.outbox_repository_port import OutboxTransactionFactory
from app.application.use_cases.messaging import conversation_events as events
from app.application.use_cases.messaging.lead_status import derive_lead_status
from app.application.use_cases.messaging.message_authorship import resolve_author_type
from app.application.use_cases.messaging.record_delivery_status import RecordDeliveryStatus
from app.core.logging import get_logger
from app.domain.entities.client import Client
from app.domain.entities.conversation_link import ConversationLink
from app.domain.entities.outbox_message import OutboxMessage
from app.domain.exceptions.outbox_exceptions import InvalidOutboxStateError
from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.outbox import DeliveryStatus
from app.domain.value_objects.phone_number import PhoneNumber


class IIncomingMessageHandler(Protocol):
    """Quien responde los mensajes de los clientes (el bot); ``APPLIED`` si respondió."""

    async def execute(self, message: IncomingClientMessage) -> GatewayEventOutcome: ...


class ProcessGatewayEvent:
    """Interpreta un evento: registra los avisos de entrega y entrega los mensajes al bot.

    Un aviso de entrega se registra en su propia transacción. Un mensaje de cliente en
    ``pending`` se pasa a ``incoming_handler``; sin él (bot apagado) solo se registra en el log.

    ``inbox`` y ``publisher`` activan la bandeja: con ``inbox``, cada mensaje asegura el
    vínculo de su conversación y un eco saliente sin fila de outbox espera a su fila; con
    ``publisher``, cada cambio se difunde como evento de mejor esfuerzo (una falla se registra
    y nunca falla el trabajo). Con ``lookup``, ``conversation.updated`` suma el estado
    comercial, el estado de la cotización y el nombre del asignado; si la consulta falla, el
    evento sale sin esos campos.
    """

    def __init__(
        self,
        *,
        transaction: OutboxTransactionFactory,
        gateway: IGatewayEventPort,
        incoming_handler: IIncomingMessageHandler | None = None,
        inbox: InboxEventUnitOfWork | None = None,
        publisher: IConversationEventPublisherPort | None = None,
        lookup: IInboxLookupPort | None = None,
    ) -> None:
        self._transaction = transaction
        self._gateway = gateway
        self._incoming_handler = incoming_handler
        self._inbox = inbox
        self._publisher = publisher
        self._lookup = lookup

    async def execute(
        self, *, raw_body: bytes, received_at: datetime, last_attempt: bool = False
    ) -> GatewayEventOutcome:
        """Procesa el cuerpo crudo del webhook.

        ``received_at`` es la hora firmada del webhook y sirve de ``at`` cuando el aviso no trae
        la suya. ``last_attempt`` indica que el trabajo no se reintentará más: un mensaje que
        sigue desconocido se registra entonces como aviso sin pareja.
        """

        # Los loggers se crean en cada llamada: structlog cachea el primero tras configurarse.
        log = get_logger("gateway_events")
        try:
            event = self._gateway.parse_event(raw_body)
        except ValidationError:
            log.warning("gateway_event_malformed")
            return GatewayEventOutcome.MALFORMED
        if isinstance(event, UnhandledGatewayEvent):
            log.info(
                "gateway_event_unhandled",
                kind=event.kind,
                direction=event.direction.value if event.direction else None,
                conversation_id=event.conversation_id,
                external_message_id=event.external_message_id,
            )
            return GatewayEventOutcome.UNHANDLED
        if isinstance(event, IncomingClientMessage):
            return await self._process_incoming(event, received_at)
        if isinstance(event, OutgoingMessageEcho):
            return await self._process_echo(event, received_at, last_attempt=last_attempt)
        return await self._process_notice(event, received_at, last_attempt=last_attempt)

    async def _process_incoming(
        self, message: IncomingClientMessage, received_at: datetime
    ) -> GatewayEventOutcome:
        """Registra el mensaje en la bandeja y, solo si la conversación es del bot, lo responde."""

        log = get_logger("gateway_events")
        recorded = False
        if self._inbox is not None and not message.is_private:
            recorded = await self._record_incoming(message, received_at)
            if message.conversation_status is not ConversationStatus.BOT:
                return GatewayEventOutcome.APPLIED
        if self._incoming_handler is None:
            log.info("client_message_unhandled", conversation_id=message.conversation_id)
            return GatewayEventOutcome.APPLIED if recorded else GatewayEventOutcome.UNHANDLED
        return await self._incoming_handler.execute(message)

    async def _record_incoming(self, message: IncomingClientMessage, received_at: datetime) -> bool:
        """Vínculo, marca del cliente y eventos; nunca impide que el bot responda."""

        log = get_logger("gateway_events")
        at = _as_utc(message.details.sent_at or received_at)
        try:
            async with self._open_inbox() as tx:
                link = await self._ensure_link(
                    tx, message.conversation_id, message.sender_phone, at
                )
                link.record_client_message(at)
                self._restart_lead_cycle_if_event_done(link, at)
                await tx.links.save(link)
                client = await _client_of(tx, link)
        except Exception as exc:
            log.error(
                "inbox_record_failed",
                conversation_id=message.conversation_id,
                error_type=type(exc).__name__,
            )
            return False
        await self._publish_message(
            external_message_id=message.external_message_id,
            conversation_id=message.conversation_id,
            direction=MessageDirection.INCOMING,
            content=message.content,
            details=message.details,
            at=at,
            outbox=None,
            link_and_client=(link, client),
            snapshot=message.snapshot,
        )
        return True

    def _open_inbox(self) -> AbstractAsyncContextManager[InboxEventTransaction]:
        if self._inbox is None:  # pragma: no cover - los llamadores ya lo comprobaron
            raise RuntimeError("La bandeja no está configurada")
        return self._inbox()

    def _restart_lead_cycle_if_event_done(self, link: ConversationLink, at: datetime) -> None:
        """Punto de llamada de D25 (B5b): reiniciar el ciclo si el ``lead_status`` es EVENT_DONE.

        El estado comercial se calcula con la cotización y el evento (``IInboxLookupPort``), que
        llegan con B5/B5b; hasta entonces no hay nada que evaluar aquí.
        """

    async def _process_echo(
        self, echo: OutgoingMessageEcho, received_at: datetime, *, last_attempt: bool
    ) -> GatewayEventOutcome:
        log = get_logger("gateway_events")
        if self._inbox is None:
            log.info(
                "gateway_event_unhandled",
                kind="message_created",
                direction=MessageDirection.OUTGOING.value,
                conversation_id=echo.conversation_id,
                external_message_id=echo.external_message_id,
            )
            return GatewayEventOutcome.UNHANDLED
        async with self._open_inbox() as tx:
            outbox = await tx.outbox.find_by_message_reference(echo.external_message_id)
            if outbox is None:
                if not last_attempt:
                    return GatewayEventOutcome.UNKNOWN_MESSAGE
                log.warning(
                    "echo_without_outbox_row",
                    conversation_id=echo.conversation_id,
                    external_message_id=echo.external_message_id,
                )
            phone = echo.snapshot.contact_phone if echo.snapshot else None
            link = await self._ensure_link(tx, echo.conversation_id, phone, received_at)
            client = await _client_of(tx, link)
        await self._publish_message(
            external_message_id=echo.external_message_id,
            conversation_id=echo.conversation_id,
            direction=MessageDirection.OUTGOING,
            content=echo.content,
            details=echo.details,
            at=_as_utc(echo.details.sent_at or received_at),
            outbox=outbox,
            link_and_client=(link, client),
            snapshot=echo.snapshot,
        )
        return GatewayEventOutcome.APPLIED

    async def _ensure_link(
        self,
        tx: InboxEventTransaction,
        conversation_id: int,
        phone: PhoneNumber | None,
        now: datetime,
    ) -> ConversationLink:
        """Asegura el vínculo; vincula al cliente solo si ya existe (D1: nunca se crea uno)."""

        client = await tx.clients.get_by_phone(phone.value) if phone is not None else None
        link = await tx.links.ensure(conversation_id, client.id if client else None, now)
        if client is not None and link.client_id is None:
            link.link_client(client.id, at=now)
            await tx.links.save(link)
        return link

    async def _publish_message(
        self,
        *,
        external_message_id: str,
        conversation_id: int,
        direction: MessageDirection,
        content: str,
        details: MessageDetails,
        at: datetime,
        outbox: OutboxMessage | None,
        link_and_client: tuple[ConversationLink, Client | None],
        snapshot: ConversationSnapshot | None,
    ) -> None:
        link, client = link_and_client
        author = resolve_author_type(direction=direction, outbox=outbox, sender=details.sender)
        batch = [
            events.message_created_event(
                external_message_id=external_message_id,
                conversation_id=conversation_id,
                direction=direction,
                author_type=author,
                content=content,
                details=details,
                at=at,
                outbox=outbox,
            )
        ]
        if snapshot is not None:
            batch.append(
                events.conversation_updated_event(
                    conversation_id=conversation_id,
                    snapshot=snapshot,
                    link=link,
                    client=client,
                    content=content,
                    details=details,
                    at=at,
                    enrichment=await self._enrich(link, snapshot),
                )
            )
        await self._publish(*batch)

    async def _enrich(
        self, link: ConversationLink, snapshot: ConversationSnapshot
    ) -> events.LeadEnrichment | None:
        """Consulta cotización y asignado fuera de toda transacción; ``None`` si falla."""

        if self._lookup is None:
            return None
        assignee = (
            link.assigned_user_id if snapshot.lifecycle is ConversationLifecycle.OPEN else None
        )
        try:
            statuses = await self._lookup.quote_statuses([link.quote_id]) if link.quote_id else {}
            names = await self._lookup.user_names([assignee]) if assignee else {}
        except Exception as exc:
            get_logger("gateway_events").warning(
                "conversation_enrichment_failed", error_type=type(exc).__name__
            )
            return None
        quote_status = statuses.get(link.quote_id) if link.quote_id else None
        return events.LeadEnrichment(
            lead_status=derive_lead_status(quote_status),
            quote_status=quote_status,
            assigned_user_name=names.get(assignee) if assignee else None,
        )

    async def _publish(self, *batch: ConversationEvent) -> None:
        """Mejor esfuerzo: registra la falla y sigue (spec 09, sección 8)."""

        if self._publisher is None:
            return
        for event in batch:
            try:
                await self._publisher.publish(event)
            except Exception as exc:
                get_logger("gateway_events").warning(
                    "conversation_event_publish_failed",
                    event_name=event.event.value,
                    error_type=type(exc).__name__,
                )

    async def _process_notice(
        self, notice: DeliveryNotice, received_at: datetime, *, last_attempt: bool
    ) -> GatewayEventOutcome:
        log = get_logger("gateway_events")
        async with self._transaction() as repository:
            known = await repository.get_by_external_id(notice.external_message_id) is not None
        if not known:
            if last_attempt:
                log.warning(
                    "delivery_notice_unmatched",
                    external_message_id=notice.external_message_id,
                    delivery_status=notice.status.value if notice.status else None,
                )
            return GatewayEventOutcome.UNKNOWN_MESSAGE

        status, error = notice.status, notice.error
        if status is None and not notice.status_in_payload and notice.conversation_id is not None:
            # La consulta a la API va fuera de toda transacción para no retener una conexión.
            report = await self._gateway.get_delivery_status(
                notice.conversation_id, notice.external_message_id
            )
            if report is not None:
                status, error = report.status, notice.error or report.error
        if status is None:
            log.debug("delivery_notice_unresolved", external_message_id=notice.external_message_id)
            return GatewayEventOutcome.UNRESOLVED

        at = _as_utc(notice.updated_at or received_at)
        failure = error if status is DeliveryStatus.FAILED else None
        async with self._transaction() as repository:
            try:
                applied = await RecordDeliveryStatus(repository).execute(
                    external_message_id=notice.external_message_id,
                    status=status,
                    error=failure,
                    at=at,
                )
            except InvalidOutboxStateError:
                log.warning(
                    "delivery_notice_invalid_state",
                    external_message_id=notice.external_message_id,
                    delivery_status=status.value,
                )
                return GatewayEventOutcome.IGNORED
            row = (
                await repository.get_by_external_id(notice.external_message_id) if applied else None
            )
        conversation_id = notice.conversation_id or (row.conversation_id if row else None)
        if applied and conversation_id is not None:
            await self._publish(
                events.message_updated_event(
                    external_message_id=notice.external_message_id,
                    conversation_id=conversation_id,
                    status=status,
                    error=failure,
                    outbox=row,
                )
            )
        return GatewayEventOutcome.APPLIED if applied else GatewayEventOutcome.IGNORED


async def _client_of(tx: InboxEventTransaction, link: ConversationLink) -> Client | None:
    return await tx.clients.get_by_id(link.client_id) if link.client_id is not None else None


def _as_utc(moment: datetime) -> datetime:
    """Hora con zona UTC; una hora sin zona se interpreta como UTC."""

    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)
