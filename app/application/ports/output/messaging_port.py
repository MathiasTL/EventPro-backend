from collections.abc import Mapping, Sequence
from typing import Protocol

from app.application.dtos.messaging_dto import (
    AttachmentContent,
    ConversationMessage,
    ConversationStatus,
    ConversationSummary,
    ListSection,
    MessageReceipt,
)
from app.domain.value_objects.phone_number import PhoneNumber


class IMessagingPort(Protocol):
    """Gateway de mensajería de WhatsApp.

    Fuera de la ventana de 24 h solo ``send_template`` es válido; las demás operaciones de
    envío lanzan ``ServiceWindowClosedError``. Si el gateway no responde, todas lanzan
    ``MessagingUnavailableError``.
    """

    async def send_text(self, to: PhoneNumber, body: str) -> MessageReceipt:
        """Envía texto libre dentro de la ventana de servicio."""

    async def send_interactive_list(
        self, to: PhoneNumber, body: str, sections: Sequence[ListSection]
    ) -> MessageReceipt:
        """Envía una lista interactiva dentro de la ventana de servicio."""

    async def send_template(
        self, to: PhoneNumber, name: str, params: Mapping[str, str]
    ) -> MessageReceipt:
        """Envía una plantilla aprobada; es el único envío válido con la ventana cerrada."""

    async def send_attachment(
        self,
        to: PhoneNumber,
        data: bytes,
        filename: str,
        content_type: str,
        caption: str | None,
    ) -> MessageReceipt:
        """Envía un adjunto dentro de la ventana de servicio."""

    async def set_conversation_status(
        self, conversation_id: int, status: ConversationStatus
    ) -> None:
        """Pasa la conversación al bot o a un humano; lanza ResourceNotFoundError si no existe."""

    async def list_conversations(
        self,
        *,
        status: ConversationStatus | None = None,
        include_resolved: bool = False,
        page: int = 1,
        page_size: int = 25,
    ) -> Sequence[ConversationSummary]:
        """Bandeja de conversaciones, la más reciente primero.

        Las resueltas solo se incluyen con ``include_resolved``; cuentan como ``BOT``.
        """

    async def get_conversation(self, conversation_id: int) -> ConversationSummary:
        """Resumen de una conversación; lanza ResourceNotFoundError si no existe."""

    async def list_messages(
        self,
        conversation_id: int,
        *,
        before_id: int | None = None,
        limit: int = 50,
    ) -> Sequence[ConversationMessage]:
        """Los ``limit`` mensajes más recientes con id menor que ``before_id`` (D16).

        Se entregan en orden cronológico ascendente e incluyen los avisos de actividad; las
        notas privadas no. Lanza ResourceNotFoundError si la conversación no existe.
        """

    async def mark_conversation_read(self, conversation_id: int) -> None:
        """Reinicia el contador de no leídos (``update_last_seen`` del agente, D13)."""

    async def get_attachment(self, conversation_id: int, attachment_id: int) -> AttachmentContent:
        """Descarga un adjunto de la conversación (D17).

        Lanza ResourceNotFoundError si no pertenece a la conversación o su destino no es seguro.
        """
