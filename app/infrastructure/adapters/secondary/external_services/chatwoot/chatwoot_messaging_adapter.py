"""Adaptador de `IMessagingPort` sobre la API de aplicación de Chatwoot v4.

Resuelve teléfono -> contacto -> conversación con el token de agente y crea los mensajes con el
token del bot. No guarda estado ni reutiliza conversaciones por su cuenta: depende de que el inbox
tenga activo `lock_to_single_conversation`. Los textos de error y los logs no llevan contenido de
mensajes, códigos ni teléfonos.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from app.application.dtos.messaging_dto import (
    ConversationMessage,
    ConversationStatus,
    ConversationSummary,
    ListSection,
    MessageReceipt,
)
from app.core.logging import get_logger
from app.domain.exceptions.messaging_exceptions import (
    MessagingUnavailableError,
    ServiceWindowClosedError,
)
from app.domain.value_objects.phone_number import PhoneNumber
from app.infrastructure.adapters.secondary.external_services.chatwoot import chatwoot_payloads as cw
from app.infrastructure.adapters.secondary.external_services.chatwoot.chatwoot_client import (
    ChatwootClient,
    ChatwootToken,
)


class ChatwootMessagingAdapter:
    def __init__(
        self,
        client: ChatwootClient,
        *,
        inbox_id: int,
        template_language: str,
        template_category: str,
    ) -> None:
        self._client = client
        self._inbox_id = inbox_id
        self._template_language = template_language
        self._template_category = template_category

    # --- Envíos ----------------------------------------------------------------------------

    async def send_text(self, to: PhoneNumber, body: str) -> MessageReceipt:
        conversation_id = await self._resolve(to, requires_window=True)
        return await self._post_message(
            conversation_id, operation="send_text", json=cw.build_text_message(body)
        )

    async def send_interactive_list(
        self, to: PhoneNumber, body: str, sections: Sequence[ListSection]
    ) -> MessageReceipt:
        conversation_id = await self._resolve(to, requires_window=True)
        # El logger se crea en cada llamada: structlog cachea el primero tras configurarse.
        get_logger("chatwoot").info(
            "chatwoot_list_flattened",
            sections=len(sections),
            rows=sum(len(section.rows) for section in sections),
        )
        return await self._post_message(
            conversation_id,
            operation="send_interactive_list",
            json=cw.build_list_message(body, sections),
        )

    async def send_template(
        self, to: PhoneNumber, name: str, params: Mapping[str, str]
    ) -> MessageReceipt:
        conversation_id = await self._resolve(to, requires_window=False)
        message = cw.build_template_message(
            name, params, category=self._template_category, language=self._template_language
        )
        return await self._post_message(conversation_id, operation="send_template", json=message)

    async def send_attachment(
        self,
        to: PhoneNumber,
        data: bytes,
        filename: str,
        content_type: str,
        caption: str | None,
    ) -> MessageReceipt:
        conversation_id = await self._resolve(to, requires_window=True)
        return await self._post_message(
            conversation_id,
            operation="send_attachment",
            data=cw.build_attachment_form(caption),
            files=cw.build_attachment_files(filename, data, content_type),
        )

    # --- Lectura y estado: tareas 3.x ------------------------------------------------------

    async def set_conversation_status(
        self, conversation_id: int, status: ConversationStatus
    ) -> None:
        raise NotImplementedError("El cambio de estado de conversación aún no está implementado")

    async def list_conversations(
        self,
        *,
        status: ConversationStatus | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> Sequence[ConversationSummary]:
        raise NotImplementedError("El listado de conversaciones aún no está implementado")

    async def list_messages(
        self,
        conversation_id: int,
        *,
        before: datetime | None = None,
        limit: int = 50,
    ) -> Sequence[ConversationMessage]:
        raise NotImplementedError("El listado de mensajes aún no está implementado")

    # --- Resolución de contacto y conversación ---------------------------------------------

    async def _resolve(self, to: PhoneNumber, *, requires_window: bool) -> int:
        """Id de la conversación del teléfono; con `requires_window` exige la ventana abierta."""

        contact_id = await self._contact_id(to)
        conversation = await self._conversation(contact_id)
        if requires_window:
            await self._ensure_window_open(conversation)
        return conversation.conversation_id

    async def _contact_id(self, to: PhoneNumber) -> int:
        found = await self._client.request(
            "GET",
            "/contacts/search",
            token=ChatwootToken.AGENT,
            operation="search_contact",
            params=cw.build_contact_search_params(to),
            required_keys=(cw.PAYLOAD_KEY,),
        )
        contact_id = cw.find_contact_id(found, to)
        if contact_id is not None:
            return contact_id
        created = await self._client.request(
            "POST",
            "/contacts",
            token=ChatwootToken.AGENT,
            operation="create_contact",
            json=cw.build_contact_request(self._inbox_id, to),
            required_keys=(cw.PAYLOAD_KEY,),
        )
        return cw.parse_contact_id(created)

    async def _conversation(self, contact_id: int) -> cw.ConversationRef:
        body = await self._client.request(
            "POST",
            "/conversations",
            token=ChatwootToken.AGENT,
            operation="create_conversation",
            json=cw.build_conversation_request(self._inbox_id, contact_id),
            required_keys=(cw.ID_KEY,),
        )
        return cw.parse_conversation_ref(body)

    async def _ensure_window_open(self, conversation: cw.ConversationRef) -> None:
        can_reply = conversation.can_reply
        if can_reply is None:
            # La respuesta de creación no informa `can_reply`: se lee la conversación una vez.
            body = await self._client.request(
                "GET",
                f"/conversations/{conversation.conversation_id}",
                token=ChatwootToken.AGENT,
                operation="get_conversation",
                required_keys=(cw.ID_KEY,),
            )
            can_reply = cw.parse_conversation_ref(body).can_reply
        if can_reply is None:
            raise MessagingUnavailableError(
                f"Respuesta inesperada de Chatwoot: falta '{cw.CAN_REPLY_KEY}'"
            )
        if not can_reply:
            raise ServiceWindowClosedError(
                "La ventana de servicio de 24 h está cerrada: solo se admiten plantillas."
            )

    # --- Creación de mensajes --------------------------------------------------------------

    async def _post_message(
        self,
        conversation_id: int,
        *,
        operation: str,
        json: Mapping[str, Any] | None = None,
        data: Mapping[str, str] | None = None,
        files: Sequence[tuple[str, tuple[str, bytes, str]]] | None = None,
    ) -> MessageReceipt:
        body = await self._client.request(
            "POST",
            f"/conversations/{conversation_id}/messages",
            token=ChatwootToken.BOT,
            operation=operation,
            json=json,
            data=data,
            files=files,
            required_keys=(cw.ID_KEY, cw.CONVERSATION_ID_KEY, cw.CREATED_AT_KEY),
        )
        return cw.parse_message_receipt(body)
