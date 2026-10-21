"""Gateway de mensajería falso: registra los envíos en memoria, sin Meta ni Chatwoot.

Sirve a E2 y E5 para integrar y probar, y en desarrollo vuelca cada mensaje al log
estructurado en lugar de enviarlo.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from enum import StrEnum

from app.application.dtos.messaging_dto import (
    AttachmentContent,
    ConversationLifecycle,
    ConversationMessage,
    ConversationStatus,
    ConversationSummary,
    ListSection,
    MessageAttachment,
    MessageDirection,
    MessageReceipt,
    MessageSender,
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

# Nombre del remitente de los mensajes que el puerto crea con el token del bot.
BOT_NAME = "EventPro Bot"


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
    resolved: bool = False
    contact_name: str | None = None
    unread_count: int = 0
    messages: list[ConversationMessage] = field(default_factory=list)

    @property
    def lifecycle(self) -> ConversationLifecycle:
        if self.resolved:
            return ConversationLifecycle.RESOLVED
        return (
            ConversationLifecycle.OPEN
            if self.status is ConversationStatus.HUMAN
            else ConversationLifecycle.PENDING
        )


class FakeMessagingAdapter:
    def __init__(self, *, clock: IClockPort | None = None, log_messages: bool = False) -> None:
        self._clock = clock or SystemClockAdapter()
        self._log_messages = log_messages
        self._conversations: dict[int, _Conversation] = {}
        self._by_phone: dict[str, int] = {}
        self._sequence = 0
        self._attachment_sequence = 0
        self._attachments: dict[tuple[int, int], AttachmentContent] = {}
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
        receipt = self._deliver(
            to, requires_window=True, body=caption, attachment=(data, filename, content_type)
        )
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
        conversation = self._conversation(conversation_id)
        conversation.status = status
        conversation.resolved = False

    async def list_conversations(
        self,
        *,
        status: ConversationStatus | None = None,
        include_resolved: bool = False,
        page: int = 1,
        page_size: int = 25,
    ) -> Sequence[ConversationSummary]:
        self._ensure_available()
        conversations = [
            conversation
            for conversation in self._conversations.values()
            if (include_resolved or not conversation.resolved)
            and (status is None or conversation.status is status)
        ]
        conversations.sort(key=lambda item: item.messages[-1].sent_at, reverse=True)
        start = (max(page, 1) - 1) * page_size
        return tuple(self._summary(item) for item in conversations[start : start + page_size])

    async def get_conversation(self, conversation_id: int) -> ConversationSummary:
        return self._summary(self._conversation(conversation_id))

    async def list_messages(
        self,
        conversation_id: int,
        *,
        before_id: int | None = None,
        limit: int = 50,
    ) -> Sequence[ConversationMessage]:
        self._ensure_available()
        messages = self._conversation(conversation_id).messages
        if before_id is not None:
            messages = [message for message in messages if int(message.message_id) < before_id]
        return tuple(messages[-limit:]) if limit > 0 else ()

    async def mark_conversation_read(self, conversation_id: int) -> None:
        self._conversation(conversation_id).unread_count = 0

    async def get_attachment(self, conversation_id: int, attachment_id: int) -> AttachmentContent:
        self._conversation(conversation_id)
        content = self._attachments.get((conversation_id, attachment_id))
        if content is None:
            raise ResourceNotFoundError(f"El adjunto {attachment_id} no existe en la conversación")
        return content

    # --- Simulación del lado del cliente y de Chatwoot (solo para pruebas) --------------------

    def receive_text(self, sender: PhoneNumber, body: str, *, name: str | None = None) -> int:
        """Mensaje entrante del cliente; reabre una resuelta como pendiente. Devuelve su id."""

        return self._receive(sender, body, name=name, attachments=())

    def receive_attachment(
        self, sender: PhoneNumber, data: bytes, filename: str, content_type: str
    ) -> int:
        """Entrante con un adjunto, descargable con `get_attachment`; devuelve el id del mensaje."""

        return self._receive(sender, None, name=None, attachments=((data, filename, content_type),))

    def add_activity(self, conversation_id: int, text: str) -> None:
        """Aviso del sistema (por ejemplo, un cambio de estado): no mueve la vista previa."""

        self._append(
            self._conversation(conversation_id),
            direction=MessageDirection.ACTIVITY,
            body=text,
        )

    def resolve_conversation(self, conversation_id: int) -> None:
        self._conversation(conversation_id).resolved = True

    def _receive(
        self,
        sender: PhoneNumber,
        body: str | None,
        *,
        name: str | None,
        attachments: Sequence[tuple[bytes, str, str]],
    ) -> int:
        conversation = self._conversation_of(sender)
        if name is not None:
            conversation.contact_name = name
        if conversation.resolved:
            conversation.resolved = False
            conversation.status = ConversationStatus.BOT
        conversation.unread_count += 1
        message = self._append(
            conversation,
            direction=MessageDirection.INCOMING,
            body=body,
            sender=MessageSender.CONTACT,
            attachments=attachments,
        )
        return int(message.message_id)

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
        attachment: tuple[bytes, str, str] | None = None,
    ) -> MessageReceipt:
        self._ensure_available()
        if requires_window and not self.service_window_open:
            raise ServiceWindowClosedError(
                "La ventana de servicio de 24 h está cerrada: solo se admiten plantillas."
            )
        conversation = self._conversation_of(to)
        message = self._append(
            conversation,
            direction=MessageDirection.OUTGOING,
            body=body,
            sender=MessageSender.AGENT_BOT,
            sender_name=BOT_NAME,
            attachments=(attachment,) if attachment is not None else (),
        )
        return MessageReceipt(message.message_id, conversation.id, message.sent_at)

    def _conversation_of(self, phone: PhoneNumber) -> _Conversation:
        conversation_id = self._by_phone.get(phone.value)
        if conversation_id is None:
            conversation_id = len(self._conversations) + 1
            self._conversations[conversation_id] = _Conversation(id=conversation_id, phone=phone)
            self._by_phone[phone.value] = conversation_id
        return self._conversations[conversation_id]

    def _append(
        self,
        conversation: _Conversation,
        *,
        direction: MessageDirection,
        body: str | None,
        sender: MessageSender | None = None,
        sender_name: str | None = None,
        attachments: Sequence[tuple[bytes, str, str]] = (),
    ) -> ConversationMessage:
        self._sequence += 1
        # Un reloj fijo no debe reordenar el historial: el microsegundo extra desempata.
        sent_at = self._clock.utcnow() + timedelta(microseconds=self._sequence)
        stored = tuple(self._store(conversation.id, *entry) for entry in attachments)
        message = ConversationMessage(
            message_id=str(self._sequence),
            conversation_id=conversation.id,
            direction=direction,
            body=body,
            sent_at=sent_at,
            attachment_filename=stored[0].filename if stored else None,
            sender=sender,
            sender_name=sender_name,
            status=None if direction is MessageDirection.ACTIVITY else "sent",
            content_type="text",
            attachments=stored,
        )
        conversation.messages.append(message)
        return message

    def _store(
        self, conversation_id: int, data: bytes, filename: str, content_type: str
    ) -> MessageAttachment:
        self._attachment_sequence += 1
        attachment_id = self._attachment_sequence
        self._attachments[(conversation_id, attachment_id)] = AttachmentContent(
            data, content_type, filename
        )
        return MessageAttachment(
            attachment_id=attachment_id,
            file_type="image" if content_type.startswith("image/") else "file",
            content_type=content_type,
            extension=filename.rsplit(".", 1)[-1] if "." in filename else None,
            file_size=len(data),
            filename=filename,
        )

    def _summary(self, conversation: _Conversation) -> ConversationSummary:
        visible = [m for m in conversation.messages if m.direction is not MessageDirection.ACTIVITY]
        last = visible[-1] if visible else None
        preview = None
        if last is not None:
            preview = (last.body or "").strip()[:120] or ("[Adjunto]" if last.attachments else None)
        return ConversationSummary(
            conversation_id=conversation.id,
            phone=conversation.phone,
            status=conversation.status,
            service_window_open=self.service_window_open,
            last_message_at=last.sent_at if last is not None else None,
            lifecycle=conversation.lifecycle,
            contact_name=conversation.contact_name,
            unread_count=conversation.unread_count,
            last_message_preview=preview,
        )

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
