"""Adaptador de `IGatewayEventPort` sobre los webhooks y la API de Chatwoot.

Interpreta el cuerpo crudo de un webhook y, cuando el aviso no informa el estado del mensaje,
lo consulta con el token de agente. Los logs y los textos de error no llevan contenido de
mensajes, nombres ni teléfonos.
"""

import json
from collections.abc import Mapping
from typing import Any

from app.application.dtos.gateway_event_dto import (
    DeliveryNotice,
    DeliveryReport,
    GatewayEvent,
    IncomingClientMessage,
    UnhandledGatewayEvent,
)
from app.application.dtos.messaging_dto import MessageDirection
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError, ValidationError
from app.infrastructure.adapters.secondary.external_services.chatwoot import chatwoot_payloads as cw
from app.infrastructure.adapters.secondary.external_services.chatwoot.chatwoot_client import (
    ChatwootClient,
    ChatwootToken,
)

_UNKNOWN_EVENT = "unknown"


class ChatwootEventGateway:
    """`client` es `None` cuando Chatwoot no está configurado: la consulta no se puede hacer."""

    def __init__(self, client: ChatwootClient | None) -> None:
        self._client = client

    # --- Webhooks --------------------------------------------------------------------------

    def parse_event(self, raw_body: bytes) -> GatewayEvent:
        body = _decode_object(raw_body)
        kind = body.get(cw.EVENT_KEY)
        if not isinstance(kind, str) or not kind:
            return UnhandledGatewayEvent(
                kind=_UNKNOWN_EVENT, direction=None, conversation_id=None, external_message_id=None
            )
        direction = cw.decode_direction(body.get(cw.MESSAGE_TYPE_KEY))
        # Una nota privada no viaja por WhatsApp: no tiene aviso de entrega.
        is_note = body.get(cw.PRIVATE_KEY) is True
        if (
            kind == cw.EVENT_MESSAGE_UPDATED
            and direction is MessageDirection.OUTGOING
            and not is_note
        ):
            return _delivery_notice(body)
        if kind == cw.EVENT_MESSAGE_CREATED and direction is MessageDirection.INCOMING:
            message = _incoming_message(body)
            if message is not None:
                return message
        return _unhandled(kind, body, direction)

    # --- API -------------------------------------------------------------------------------

    async def get_delivery_status(
        self, conversation_id: int, external_message_id: str
    ) -> DeliveryReport | None:
        """Lee el mensaje con el cursor `before = id + 1`: queda como el último de la página."""

        if self._client is None or not external_message_id.isdecimal():
            return None
        message_id = int(external_message_id)
        try:
            body = await self._client.request(
                "GET",
                f"/conversations/{conversation_id}/messages",
                token=ChatwootToken.AGENT,
                operation="get_delivery_status",
                params=cw.build_message_list_params(message_id + 1),
                not_found_is_missing=True,
            )
        except ResourceNotFoundError:
            return None
        for item in cw.message_items(body):
            if item.get(cw.ID_KEY) == message_id:
                return DeliveryReport(
                    status=cw.delivery_status_from(item.get(cw.STATUS_KEY)),
                    error=cw.external_error(item),
                )
        return None


def _decode_object(raw_body: bytes) -> Mapping[str, Any]:
    try:
        body = json.loads(raw_body)
    except ValueError:
        raise ValidationError("El cuerpo del webhook no es JSON válido") from None
    if not isinstance(body, dict):
        raise ValidationError("El cuerpo del webhook no es un objeto JSON")
    return body


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _conversation_id(body: Mapping[str, Any]) -> int | None:
    conversation = body.get(cw.CONVERSATION_KEY)
    if isinstance(conversation, Mapping):
        return _int_or_none(conversation.get(cw.ID_KEY))
    return None


def _delivery_notice(body: Mapping[str, Any]) -> DeliveryNotice:
    message_id = _int_or_none(body.get(cw.ID_KEY))
    if message_id is None:
        raise ValidationError("El aviso de entrega no trae el identificador del mensaje")
    # El estado y la hora del mensaje solo viajan en su copia incrustada en la conversación.
    embedded = cw.embedded_message(body) or {}
    return DeliveryNotice(
        external_message_id=str(message_id),
        conversation_id=_conversation_id(body),
        status=cw.delivery_status_from(embedded.get(cw.STATUS_KEY)),
        error=cw.external_error(body) or cw.external_error(embedded),
        updated_at=cw.event_time(embedded.get(cw.UPDATED_AT_KEY)),
        status_in_payload=embedded.get(cw.STATUS_KEY) is not None,
    )


def _incoming_message(body: Mapping[str, Any]) -> IncomingClientMessage | None:
    """Mensaje del cliente; `None` si no trae lo mínimo para responder (queda como no atendido).

    El estado de la conversación viaja en `conversation.status`: solo `pending` (bot) y `open`
    (encargado) se reconocen.
    """

    message_id = _int_or_none(body.get(cw.ID_KEY))
    conversation_id = _conversation_id(body)
    conversation = body.get(cw.CONVERSATION_KEY)
    status = cw.conversation_status_of(
        conversation.get(cw.STATUS_KEY) if isinstance(conversation, Mapping) else None
    )
    phone = cw.incoming_sender_phone(body)
    if message_id is None or conversation_id is None or status is None or phone is None:
        return None
    content = body.get(cw.CONTENT_KEY)
    return IncomingClientMessage(
        external_message_id=str(message_id),
        conversation_id=conversation_id,
        conversation_status=status,
        sender_phone=phone,
        content=content if isinstance(content, str) else "",
        is_private=body.get(cw.PRIVATE_KEY) is True,
    )


def _unhandled(
    kind: str, body: Mapping[str, Any], direction: MessageDirection | None
) -> UnhandledGatewayEvent:
    """Evento que solo se registra: en los de conversación, `id` es el de la conversación."""

    if kind.startswith(cw.EVENT_CONVERSATION_PREFIX):
        return UnhandledGatewayEvent(
            kind=kind,
            direction=None,
            conversation_id=_int_or_none(body.get(cw.ID_KEY)),
            external_message_id=None,
        )
    message_id = _int_or_none(body.get(cw.ID_KEY))
    return UnhandledGatewayEvent(
        kind=kind,
        direction=direction,
        conversation_id=_conversation_id(body),
        external_message_id=str(message_id) if message_id is not None else None,
    )
