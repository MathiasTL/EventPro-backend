"""Comprobante de pago por WhatsApp: lo guarda, registra el adelanto y dice qué responder.

Lo comparten el agente y el motor de menús. Descarga el primer adjunto imagen o PDF, lo guarda
como evidencia y registra el adelanto en una unidad de trabajo propia; la respuesta y la
derivación a un encargado las ejecuta quien llama con el resultado. Los logs llevan
identificadores, nunca el contenido del archivo ni el texto del cliente.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from app.application.dtos.gateway_event_dto import IncomingClientMessage
from app.application.dtos.messaging_dto import MessageAttachment
from app.application.ports.output.bot_unit_of_work_port import BotUnitOfWork
from app.application.ports.output.messaging_port import IMessagingPort
from app.application.ports.output.payment_evidence_storage_port import (
    IPaymentEvidenceStoragePort,
)
from app.application.use_cases.bot import bot_messages as texts
from app.core.logging import get_logger
from app.domain.exceptions.messaging_exceptions import MessagingUnavailableError
from app.domain.exceptions.resource_exceptions import ResourceInUseError, ResourceNotFoundError
from app.domain.exceptions.storage_exceptions import EvidenceValidationError

# Motivo interno de la derivación (``map_reason`` lo traduce a ``HandoffReason``).
RECEIPT_HANDOFF_REASON = "payment_receipt"
_PDF_CONTENT_TYPE = "application/pdf"


@dataclass(frozen=True)
class ReceiptResult:
    """``handoff`` es ``False`` solo si hay que pedir el comprobante de nuevo."""

    reply: str
    handoff: bool


def has_attachments(message: IncomingClientMessage) -> bool:
    """Solo un mensaje con adjunto cuenta como comprobante; texto, emojis y stickers no."""

    return bool(message.details.attachments)


def first_receipt_attachment(attachments: Sequence[MessageAttachment]) -> MessageAttachment | None:
    """Primer adjunto que es imagen o PDF; el contenido real lo valida el almacenamiento."""

    return next((item for item in attachments if _is_image_or_pdf(item)), None)


def _is_image_or_pdf(attachment: MessageAttachment) -> bool:
    content_type = (attachment.content_type or "").lower()
    extension = (attachment.extension or "").lower().lstrip(".")
    return (
        attachment.file_type == "image"
        or content_type.startswith("image/")
        or content_type == _PDF_CONTENT_TYPE
        or extension == "pdf"
    )


class PaymentReceiptHandler:
    def __init__(
        self,
        *,
        unit_of_work: BotUnitOfWork,
        messaging: IMessagingPort,
        storage: IPaymentEvidenceStoragePort,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._messaging = messaging
        self._storage = storage

    async def handle(self, message: IncomingClientMessage, quote_id: UUID) -> ReceiptResult:
        """Registra el comprobante del mensaje; un error inesperado se propaga a quien llama."""

        log = get_logger("bot")
        attachment = first_receipt_attachment(message.details.attachments)
        if attachment is None or self._too_big(attachment):
            log.info("bot_receipt_rejected", conversation_id=message.conversation_id)
            return ReceiptResult(texts.RECEIPT_UNREADABLE, handoff=False)
        try:
            content = await self._messaging.get_attachment(
                message.conversation_id, attachment.attachment_id
            )
        except (MessagingUnavailableError, ResourceNotFoundError) as error:
            # El encargado ve el archivo en la conversación aunque no se haya podido guardar.
            log.warning(
                "bot_receipt_download_failed",
                conversation_id=message.conversation_id,
                error_type=type(error).__name__,
            )
            return ReceiptResult(texts.RECEIPT_REGISTERED, handoff=True)
        try:
            evidence_path = await self._storage.store(
                data=content.data,
                content_type=content.content_type,
                original_filename=content.filename,
            )
        except EvidenceValidationError:
            log.info("bot_receipt_rejected", conversation_id=message.conversation_id)
            return ReceiptResult(texts.RECEIPT_UNREADABLE, handoff=False)
        try:
            async with self._unit_of_work() as tx:
                await tx.register_receipt.execute(quote_id, evidence_path)
        except ResourceInUseError:
            # Ya hay un adelanto pendiente: no se duplica y el encargado lo ve igual.
            log.info("bot_receipt_advance_exists", conversation_id=message.conversation_id)
            await self._discard(evidence_path, message.conversation_id)
            return ReceiptResult(texts.RECEIPT_REGISTERED, handoff=True)
        except Exception:
            await self._discard(evidence_path, message.conversation_id)
            raise
        log.info("bot_receipt_registered", conversation_id=message.conversation_id)
        return ReceiptResult(texts.RECEIPT_REGISTERED, handoff=True)

    def _too_big(self, attachment: MessageAttachment) -> bool:
        size = attachment.file_size
        return size is not None and size > self._storage.max_bytes()

    async def _discard(self, evidence_path: str, conversation_id: int) -> None:
        """Borra el archivo que quedó sin pago; de mejor esfuerzo."""

        try:
            await self._storage.delete(evidence_path)
        except Exception as error:
            get_logger("bot").error(
                "bot_receipt_cleanup_failed",
                conversation_id=conversation_id,
                error_type=type(error).__name__,
            )
