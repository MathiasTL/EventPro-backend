from typing import Protocol

from app.application.dtos.gateway_event_dto import DeliveryReport, GatewayEvent


class IGatewayEventPort(Protocol):
    """Interpreta los eventos que entrega el gateway y consulta el estado de un mensaje."""

    def parse_event(self, raw_body: bytes) -> GatewayEvent:
        """Convierte el cuerpo crudo en un evento.

        Lanza ``ValidationError`` si el cuerpo no es un evento reconocible; un evento válido
        que no es un aviso de entrega se devuelve como ``UnhandledGatewayEvent``.
        """

    async def get_delivery_status(
        self, conversation_id: int, external_message_id: str
    ) -> DeliveryReport | None:
        """Consulta el estado del mensaje en el gateway.

        Devuelve ``None`` si el mensaje no se encuentra o el gateway no está configurado, y deja
        pasar ``MessagingUnavailableError`` cuando el gateway no responde.
        """
