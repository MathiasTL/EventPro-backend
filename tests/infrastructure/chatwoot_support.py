"""Chatwoot simulado para las pruebas del adaptador, sobre `httpx.MockTransport`.

`FakeChatwootServer` guarda contactos, conversaciones y mensajes en memoria y responde a las rutas
de la API de aplicación que usa el adaptador. El JSON se genera con las mismas constantes de
campo que `chatwoot_payloads.py`, de modo que adaptador y simulador comparten un solo vocabulario.
"""

import json
import re
from dataclasses import dataclass, field
from email.message import Message
from email.parser import BytesParser
from typing import Any

import httpx

from app.domain.value_objects.phone_number import PhoneNumber
from app.infrastructure.adapters.secondary.external_services.chatwoot import chatwoot_payloads as cw
from app.infrastructure.adapters.secondary.external_services.chatwoot.chatwoot_client import (
    TOKEN_HEADER,
    ChatwootClient,
)

ACCOUNT_ID = 1
INBOX_ID = 2
BOT_TOKEN = "bot-token-value-1234"
AGENT_TOKEN = "agent-token-value-5678"
BASE_URL = f"https://chatwoot.example.org/api/v1/accounts/{ACCOUNT_ID}"
FIRST_EPOCH = 1_791_813_600
WAMID = "wamid.SIMULADO0001"
# Cuerpo de error con contenido, código y teléfono: ningún log ni excepción debe repetirlo.
ERROR_BODY = "Codigo 123456 para 51999111222"

_ACCOUNT_PREFIX = f"/api/v1/accounts/{ACCOUNT_ID}"
_CONVERSATION_PATH = re.compile(r"/conversations/(\d+)")
_MESSAGES_PATH = re.compile(r"/conversations/(\d+)/messages")
_OUTGOING_TYPE = 1


@dataclass
class FakeContact:
    id: int
    name: str
    phone_number: str


@dataclass
class FakeMessage:
    id: int
    conversation_id: int
    content: str | None
    created_at: int


@dataclass
class FakeConversation:
    id: int
    inbox_id: int
    contact_id: int
    can_reply: bool
    status: str = "pending"
    messages: list[FakeMessage] = field(default_factory=list)
    last_activity_at: int = FIRST_EPOCH


class FakeChatwootServer:
    """Servidor en memoria; `handler` se entrega a `httpx.MockTransport`."""

    def __init__(self) -> None:
        self.contacts: dict[int, FakeContact] = {}
        self.conversations: dict[int, FakeConversation] = {}
        # Interruptores de escenario.
        self.window_open = True
        self.down = False
        self.lock_to_single_conversation = True
        self.new_conversation_can_reply = True
        self.conversation_create_has_can_reply = True
        self.conversation_has_can_reply = True
        # Fallos al crear mensajes: una excepción de transporte o un estado HTTP con cuerpo.
        self.message_post_error: Exception | None = None
        self.message_post_status: int | None = None
        # Registro de lo recibido: (método, ruta sin el prefijo de la cuenta, tipo de token).
        self.log: list[tuple[str, str, str]] = []
        self.requests: list[httpx.Request] = []
        self._epoch = FIRST_EPOCH
        self._next_message_id = 1

    # --- Preparación -----------------------------------------------------------------------

    def add_contact(self, phone: PhoneNumber) -> int:
        contact_id = len(self.contacts) + 1
        self.contacts[contact_id] = FakeContact(contact_id, phone.value, phone.value)
        return contact_id

    def client(self) -> ChatwootClient:
        http = httpx.AsyncClient(transport=httpx.MockTransport(self.handler), base_url=BASE_URL)
        return ChatwootClient(http, bot_token=BOT_TOKEN, agent_token=AGENT_TOKEN)

    # --- Enrutado --------------------------------------------------------------------------

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("Chatwoot simulado caído", request=request)
        path = request.url.path
        if not path.startswith(f"{_ACCOUNT_PREFIX}/"):
            return httpx.Response(404)
        relative = path.removeprefix(_ACCOUNT_PREFIX)
        self.requests.append(request)
        self.log.append((request.method, relative, self._token_kind(request)))
        return self._route(request, relative)

    @staticmethod
    def _token_kind(request: httpx.Request) -> str:
        token = request.headers.get(TOKEN_HEADER)
        return {BOT_TOKEN: "bot", AGENT_TOKEN: "agent"}.get(token or "", "unknown")

    def _route(self, request: httpx.Request, path: str) -> httpx.Response:
        method = request.method
        if method == "GET" and path == "/contacts/search":
            return self._search_contacts(request)
        if method == "POST" and path == "/contacts":
            return self._create_contact(request)
        if method == "POST" and path == "/conversations":
            return self._create_conversation(request)
        if method == "GET" and (match := _CONVERSATION_PATH.fullmatch(path)):
            return self._get_conversation(int(match.group(1)))
        if method == "POST" and (match := _MESSAGES_PATH.fullmatch(path)):
            return self._create_message(request, int(match.group(1)))
        return httpx.Response(404)

    # --- Contactos -------------------------------------------------------------------------

    def _search_contacts(self, request: httpx.Request) -> httpx.Response:
        query = request.url.params.get(cw.SEARCH_QUERY_PARAM, "")
        found = [
            self._contact_json(contact)
            for contact in self.contacts.values()
            if query in contact.phone_number
        ]
        return httpx.Response(200, json={cw.PAYLOAD_KEY: found})

    def _create_contact(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        contact_id = len(self.contacts) + 1
        contact = FakeContact(contact_id, body[cw.NAME_KEY], body[cw.PHONE_NUMBER_KEY])
        self.contacts[contact_id] = contact
        return httpx.Response(
            200, json={cw.PAYLOAD_KEY: {cw.CONTACT_KEY: self._contact_json(contact)}}
        )

    @staticmethod
    def _contact_json(contact: FakeContact) -> dict[str, Any]:
        return {
            cw.ID_KEY: contact.id,
            cw.NAME_KEY: contact.name,
            cw.PHONE_NUMBER_KEY: contact.phone_number,
        }

    # --- Conversaciones --------------------------------------------------------------------

    def _create_conversation(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        inbox_id, contact_id = body[cw.INBOX_ID_KEY], body[cw.CONTACT_ID_KEY]
        conversation = (
            self._existing(inbox_id, contact_id) if self.lock_to_single_conversation else None
        )
        if conversation is None:
            conversation = FakeConversation(
                id=len(self.conversations) + 1,
                inbox_id=inbox_id,
                contact_id=contact_id,
                can_reply=self.new_conversation_can_reply,
                last_activity_at=self._epoch,
            )
            self.conversations[conversation.id] = conversation
        return httpx.Response(
            200,
            json=self._conversation_json(
                conversation, include_can_reply=self.conversation_create_has_can_reply
            ),
        )

    def _existing(self, inbox_id: int, contact_id: int) -> FakeConversation | None:
        return next(
            (
                conversation
                for conversation in self.conversations.values()
                if conversation.inbox_id == inbox_id and conversation.contact_id == contact_id
            ),
            None,
        )

    def _get_conversation(self, conversation_id: int) -> httpx.Response:
        conversation = self.conversations.get(conversation_id)
        if conversation is None:
            return httpx.Response(404)
        return httpx.Response(
            200,
            json=self._conversation_json(
                conversation, include_can_reply=self.conversation_has_can_reply
            ),
        )

    def _conversation_json(
        self, conversation: FakeConversation, *, include_can_reply: bool
    ) -> dict[str, Any]:
        rendered: dict[str, Any] = {
            cw.ID_KEY: conversation.id,
            cw.INBOX_ID_KEY: conversation.inbox_id,
            cw.STATUS_KEY: conversation.status,
            cw.META_KEY: {
                cw.SENDER_KEY: self._contact_json(self.contacts[conversation.contact_id])
            },
            cw.LAST_ACTIVITY_AT_KEY: conversation.last_activity_at,
        }
        if include_can_reply:
            rendered[cw.CAN_REPLY_KEY] = self.window_open and conversation.can_reply
        return rendered

    # --- Mensajes --------------------------------------------------------------------------

    def _create_message(self, request: httpx.Request, conversation_id: int) -> httpx.Response:
        conversation = self.conversations.get(conversation_id)
        if conversation is None:
            return httpx.Response(404)
        if self.message_post_error is not None:
            raise self.message_post_error
        if self.message_post_status is not None:
            # El cuerpo de error trae contenido y teléfono a propósito: no debe filtrarse.
            return httpx.Response(self.message_post_status, text=ERROR_BODY)
        self._epoch += 1
        message = FakeMessage(
            id=self._next_message_id,
            conversation_id=conversation_id,
            content=self._message_content(request),
            created_at=self._epoch,
        )
        self._next_message_id += 1
        conversation.messages.append(message)
        conversation.last_activity_at = message.created_at
        return httpx.Response(200, json=self._message_json(message))

    @staticmethod
    def _message_content(request: httpx.Request) -> str | None:
        if request.headers.get("content-type", "").startswith("multipart/"):
            caption = next(
                (part for part in parse_multipart(request) if part.name == cw.CONTENT_KEY), None
            )
            return caption.data.decode() if caption is not None else None
        content = json.loads(request.content).get(cw.CONTENT_KEY)
        return content if isinstance(content, str) else None

    @staticmethod
    def _message_json(message: FakeMessage) -> dict[str, Any]:
        return {
            cw.ID_KEY: message.id,
            cw.CONVERSATION_ID_KEY: message.conversation_id,
            cw.CONTENT_KEY: message.content,
            cw.MESSAGE_TYPE_KEY: _OUTGOING_TYPE,
            cw.PRIVATE_KEY: False,
            # Chatwoot completa el WAMID de forma asíncrona; el adaptador nunca debe usarlo.
            cw.SOURCE_ID_KEY: WAMID,
            cw.CREATED_AT_KEY: message.created_at,
        }


@dataclass(frozen=True)
class MultipartPart:
    name: str
    filename: str | None
    content_type: str | None
    data: bytes


def parse_multipart(request: httpx.Request) -> list[MultipartPart]:
    """Partes de una petición `multipart/form-data`, con nombre, archivo y tipo de contenido."""

    header = b"Content-Type: " + request.headers["content-type"].encode() + b"\r\n\r\n"
    message = BytesParser().parsebytes(header + request.content)
    parts: list[MultipartPart] = []
    for part in message.get_payload():
        assert isinstance(part, Message)
        data = part.get_payload(decode=True)
        assert isinstance(data, bytes)
        parts.append(
            MultipartPart(
                name=str(part.get_param("name", header="content-disposition")),
                filename=part.get_filename(),
                content_type=part.get("content-type"),
                data=data,
            )
        )
    return parts
