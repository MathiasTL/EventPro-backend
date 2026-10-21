"""Leer el adjunto de una conversación para el proxy de medios (spec 09, sección 11, D17)."""

from app.application.dtos.messaging_dto import AttachmentContent
from app.application.ports.output.messaging_port import IMessagingPort


class GetConversationAttachment:
    """Delega en el puerto, que valida la pertenencia a la conversación y el destino seguro."""

    def __init__(self, messaging: IMessagingPort) -> None:
        self._messaging = messaging

    async def execute(self, conversation_id: int, attachment_id: int) -> AttachmentContent:
        """Lanza ``ResourceNotFoundError`` (no existe, es de otra conversación o su destino no
        es seguro) o ``MessagingUnavailableError`` si Chatwoot falla.
        """

        return await self._messaging.get_attachment(conversation_id, attachment_id)
