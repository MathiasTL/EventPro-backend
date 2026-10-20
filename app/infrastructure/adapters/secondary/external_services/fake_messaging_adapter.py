"""Gateway de mensajería falso: registra los envíos en memoria, sin Meta ni Chatwoot.

Sirve a E2 y E5 para integrar y probar, y en desarrollo vuelca cada mensaje al log
estructurado en lugar de enviarlo.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum

from app.application.dtos.messaging_dto import (
    ConversationMessage,
    ConversationStatus,
    ConversationSummary,
    ListSection,
    MessageDirection,
    MessageReceipt,
)
from app.application.ports.output.clock_port import IClockPort
from app.core.logging import get_logger
from app.domain.exceptions.messaging_exceptions import (
    MessagingUnavailableError,
    ServiceWindowClosedError,
)
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError
from app.domain.value_objects.phone_number import PhoneNumber
from app.infrastructure.adapters.secondary.external_services.system_clock_adapter import (
    SystemClockAdapter,
)


class SentMessageKind(StrEnum):
    TEXT = "TEXT"
    INTERACTIVE_LIST = "INTERACTIVE_LIST"
    TEMPLATE = "TEMPLATE"
    ATTACHMENT = "ATTACHMENT"


@dataclass(frozen=True)
class SentMessage:
    """Mensaje saliente registrado para aserciones en las pruebas."""

    kind: SentMessageKind
    to: PhoneNumber
    receipt: MessageReceipt
    body: str | None = None
    template_name: str | None = None
    template_params: Mapping[str, str] = field(default_factory=dict)
    sections: Sequence[ListSection] = ()
    filename: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None


@dataclass
class _Conversation:
    id: int
    phone: PhoneNumber
    status: ConversationStatus = ConversationStatus.BOT
    messages: list[ConversationMessage] = field(default_factory=list)


class FakeMessagingAdapter:
    def __init__(self, *, clock: IClockPort | None = None, log_messages: bool = False) -> None:
        self._clock = clock or SystemClockAdapter()
        self._log_messages = log_messages
        self._conversations: dict[int, _Conversation] = {}
        self._by_phone: dict[str, int] = {}
        self._sequence = 0
        self.sent: list[SentMessage] = []
        self.service_window_open = True
        self.unavailable = False

    async def send_text(self, to: PhoneNumber, body: str) -> MessageReceipt:
        receipt = self._deliver(to, requires_window=True, body=body)
        self._record(SentMessageKind.TEXT, to, receipt, body=body)
        return receipt

    async def send_interactive_list(
        self, to: PhoneNumber, body: str, sections: Sequence[ListSection]
    ) -> MessageReceipt:
        receipt = self._deliver(to, requires_window=True, body=body)
        self._record(SentMessageKind.INTERACTIVE_LIST, to, receipt, body=body, sections=sections)
        return receipt

    async def send_template(
        self, to: PhoneNumber, name: str, params: Mapping[str, str]
    ) -> MessageReceipt:
        receipt = self._deliver(to, requires_window=False, body=f"[plantilla:{name}]")
        self._record(
            SentMessageKind.TEMPLATE,
            to,
            receipt,
            template_name=name,
            template_params=dict(params),
        )
        return receipt

    async def send_attachment(
        self,
        to: PhoneNumber,
        data: bytes,
        filename: str,
        content_type: str,
        caption: str | None,
    ) -> MessageReceipt:
        receipt = self._deliver(to, requires_window=True, body=caption, filename=filename)
        self._record(
            SentMessageKind.ATTACHMENT,
            to,
            receipt,
            body=caption,
            filename=filename,
            content_type=content_type,
            size_bytes=len(data),
        )
        return receipt

    async def set_conversation_status(
        self, conversation_id: int, status: ConversationStatus
    ) -> None:
        self._conversation(conversation_id).status = status

    async def list_conversations(
        self,
        *,
        status: ConversationStatus | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> Sequence[ConversationSummary]:
        self._ensure_available()
        conversations = [
            conversation
            for conversation in self._conversations.values()
            if status is None or conversation.status is status
        ]
        conversations.sort(key=lambda item: item.messages[-1].sent_at, reverse=True)
        start = (max(page, 1) - 1) * page_size
        return tuple(
            ConversationSummary(
                conversation_id=item.id,
                phone=item.phone,
                status=item.status,
                service_window_open=self.service_window_open,
                last_message_at=item.messages[-1].sent_at,
            )
            for item in conversations[start : start + page_size]
        )

    async def list_messages(
        self,
        conversation_id: int,
        *,
        before: datetime | None = None,
        limit: int = 50,
    ) -> Sequence[ConversationMessage]:
        self._ensure_available()
        messages = self._conversation(conversation_id).messages
        if before is not None:
            messages = [message for message in messages if message.sent_at < before]
        return tuple(messages[-limit:]) if limit > 0 else ()

    def _ensure_available(self) -> None:
        if self.unavailable:
            raise MessagingUnavailableError("El gateway de mensajería no responde.")

    def _conversation(self, conversation_id: int) -> _Conversation:
        self._ensure_available()
        conversation = self._conversations.get(conversation_id)
        if conversation is None:
            raise ResourceNotFoundError(f"La conversación {conversation_id} no existe")
        return conversation

    def _deliver(
        self,
        to: PhoneNumber,
        *,
        requires_window: bool,
        body: str | None,
        filename: str | None = None,
    ) -> MessageReceipt:
        self._ensure_available()
        if requires_window and not self.service_window_open:
            raise ServiceWindowClosedError(
                "La ventana de servicio de 24 h está cerrada: solo se admiten plantillas."
            )
        conversation_id = self._by_phone.get(to.value)
        if conversation_id is None:
            conversation_id = len(self._conversations) + 1
            self._conversations[conversation_id] = _Conversation(id=conversation_id, phone=to)
            self._by_phone[to.value] = conversation_id
        self._sequence += 1
        # Un reloj fijo no debe reordenar el historial: el microsegundo extra desempata.
        sent_at = self._clock.utcnow() + timedelta(microseconds=self._sequence)
        receipt = MessageReceipt(f"fake-{self._sequence}", conversation_id, sent_at)
        self._conversations[conversation_id].messages.append(
            ConversationMessage(
                message_id=receipt.message_id,
                conversation_id=conversation_id,
                direction=MessageDirection.OUTGOING,
                body=body,
                sent_at=sent_at,
                attachment_filename=filename,
            )
        )
        return receipt

    def _record(
        self, kind: SentMessageKind, to: PhoneNumber, receipt: MessageReceipt, **details: object
    ) -> None:
        self.sent.append(SentMessage(kind=kind, to=to, receipt=receipt, **details))  # type: ignore[arg-type]
        if self._log_messages:
            # El logger se crea en cada llamada: structlog cachea el primero tras configurarse.
            get_logger("fake_messaging").info(
                "fake_message_sent",
                kind=kind.value,
                to=f"{to.value[:-3]}***",
                message_id=receipt.message_id,
                conversation_id=receipt.conversation_id,
                **{key: value for key, value in details.items() if key != "sections"},
            )
