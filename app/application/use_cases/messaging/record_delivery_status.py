"""Caso de uso RecordDeliveryStatus: aplica el aviso de entrega de WhatsApp a su mensaje."""

from datetime import datetime

from app.application.ports.output.outbox_repository_port import IOutboxRepositoryPort
from app.core.logging import get_logger
from app.domain.value_objects.outbox import DeliveryStatus


class RecordDeliveryStatus:
    """Busca por ``external_message_id`` y aplica ``record_delivery``; no hace ``commit``."""

    def __init__(self, repository: IOutboxRepositoryPort) -> None:
        self._repository = repository

    async def execute(
        self,
        *,
        external_message_id: str,
        status: DeliveryStatus,
        error: str | None,
        at: datetime,
    ) -> bool:
        """Devuelve ``True`` si el aviso cambió el mensaje.

        Un identificador desconocido se ignora y se registra (puede ser un mensaje que el
        encargado envió a mano desde Chatwoot); un aviso fuera de orden también se ignora.
        """

        message = await self._repository.get_by_external_id(external_message_id, for_update=True)
        if message is None:
            # El logger se crea en cada llamada: structlog cachea el primero tras configurarse.
            get_logger("outbox").info(
                "outbox_delivery_unknown_message",
                external_message_id=external_message_id,
                delivery_status=status.value,
            )
            return False
        applied = message.record_delivery(status=status, error=error, at=at)
        if applied:
            await self._repository.save(message)
        return applied
