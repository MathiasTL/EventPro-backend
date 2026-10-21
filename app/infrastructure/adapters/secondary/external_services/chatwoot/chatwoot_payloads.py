"""Formato de intercambio con Chatwoot: constructores de peticiones y lectores de respuestas.

Todos los nombres de campo de Chatwoot son constantes de este módulo. Las formas de las respuestas
y de los webhooks están contrastadas con capturas reales de Chatwoot v4.18.0 (ver
`tests/fixtures/chatwoot/README.md`); los adjuntos se capturaron el 2026-10-20.
Las funciones son puras; los fallos de forma se informan como `MessagingUnavailableError` con un
texto fijo que nombra la clave ausente y nunca el contenido recibido.
"""

import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import unquote, urlsplit

from app.application.dtos.messaging_dto import (
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
from app.domain.exceptions.messaging_exceptions import MessagingUnavailableError
from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.outbox import DeliveryStatus
from app.domain.value_objects.phone_number import PhoneNumber

# --- Claves de las respuestas -------------------------------------------------------------
ID_KEY = "id"
PAYLOAD_KEY = "payload"
DATA_KEY = "data"
CONTACT_KEY = "contact"
PHONE_NUMBER_KEY = "phone_number"
CONVERSATION_ID_KEY = "conversation_id"
CREATED_AT_KEY = "created_at"
CONTENT_KEY = "content"
MESSAGE_TYPE_KEY = "message_type"
PRIVATE_KEY = "private"
# WAMID del mensaje: el adaptador no lo lee (el recibo usa el id de Chatwoot); lo usa el simulador.
SOURCE_ID_KEY = "source_id"
ATTACHMENTS_KEY = "attachments"
DATA_URL_KEY = "data_url"
STATUS_KEY = "status"
CAN_REPLY_KEY = "can_reply"
MESSAGES_KEY = "messages"
META_KEY = "meta"
SENDER_KEY = "sender"
LAST_ACTIVITY_AT_KEY = "last_activity_at"
UNREAD_COUNT_KEY = "unread_count"
LAST_NON_ACTIVITY_KEY = "last_non_activity_message"
ASSIGNEE_KEY = "assignee"
TYPE_KEY = "type"
FILE_TYPE_KEY = "file_type"
EXTENSION_KEY = "extension"
FILE_SIZE_KEY = "file_size"
# Webhooks: nombre del evento, hora de actualización (del mensaje incrustado), conversación y
# motivo de un envío fallido.
EVENT_KEY = "event"
UPDATED_AT_KEY = "updated_at"
CONVERSATION_KEY = "conversation"
EXTERNAL_ERROR_KEY = "external_error"

# --- Claves y valores de las peticiones ---------------------------------------------------
INBOX_ID_KEY = "inbox_id"
CONTACT_ID_KEY = "contact_id"
NAME_KEY = "name"
CATEGORY_KEY = "category"
LANGUAGE_KEY = "language"
CONTENT_TYPE_KEY = "content_type"
CONTENT_ATTRIBUTES_KEY = "content_attributes"
ITEMS_KEY = "items"
ITEM_TITLE_KEY = "title"
ITEM_VALUE_KEY = "value"
TEMPLATE_PARAMS_KEY = "template_params"
PROCESSED_PARAMS_KEY = "processed_params"
BODY_PARAMS_KEY = "body"
SEARCH_QUERY_PARAM = "q"
PAGE_PARAM = "page"
BEFORE_PARAM = "before"
SORT_BY_PARAM = "sort_by"
SORT_LAST_ACTIVITY_DESC = "last_activity_at_desc"
ATTACHMENT_FILE_FIELD = "attachments[]"

EVENT_MESSAGE_CREATED = "message_created"
EVENT_MESSAGE_UPDATED = "message_updated"
EVENT_CONVERSATION_PREFIX = "conversation_"

OUTGOING_MESSAGE_TYPE = "outgoing"
INPUT_SELECT_CONTENT_TYPE = "input_select"
TEMPLATE_PLACEHOLDER = "[plantilla:{name}]"

# --- Valores que Chatwoot devuelve --------------------------------------------------------
STATUS_PENDING = "pending"
STATUS_OPEN = "open"
STATUS_RESOLVED = "resolved"
STATUS_ALL = "all"
_DIRECTIONS: Mapping[int | str, MessageDirection] = {
    0: MessageDirection.INCOMING,
    "incoming": MessageDirection.INCOMING,
    1: MessageDirection.OUTGOING,
    "outgoing": MessageDirection.OUTGOING,
}
_LISTED_DIRECTIONS: Mapping[int | str, MessageDirection] = {
    **_DIRECTIONS,
    2: MessageDirection.ACTIVITY,
    "activity": MessageDirection.ACTIVITY,
}
_SENDERS: Mapping[str, MessageSender] = {
    "contact": MessageSender.CONTACT,
    "user": MessageSender.USER,
    "agent_bot": MessageSender.AGENT_BOT,
}
_LIFECYCLES: Mapping[str, ConversationLifecycle] = {
    STATUS_PENDING: ConversationLifecycle.PENDING,
    STATUS_OPEN: ConversationLifecycle.OPEN,
    STATUS_RESOLVED: ConversationLifecycle.RESOLVED,
}
_CONVERSATION_STATUSES: Mapping[str, ConversationStatus] = {
    STATUS_PENDING: ConversationStatus.BOT,
    STATUS_OPEN: ConversationStatus.HUMAN,
}
_CHATWOOT_STATUSES: Mapping[ConversationStatus, str] = {
    status: chatwoot_status for chatwoot_status, status in _CONVERSATION_STATUSES.items()
}
# Estados de un mensaje saliente que se registran; `sent` y cualquier otro no se registran.
_DELIVERY_STATUSES: Mapping[str, DeliveryStatus] = {
    "delivered": DeliveryStatus.DELIVERED,
    "read": DeliveryStatus.READ,
    "failed": DeliveryStatus.FAILED,
}

_MICROSECONDS_PER_SECOND = 1_000_000
PREVIEW_MAX_CHARS = 120
ATTACHMENT_PREVIEW = "[Adjunto]"
_NON_DIGITS = re.compile(r"\D")


@dataclass(frozen=True)
class ConversationRef:
    """Conversación resuelta; `can_reply` es `None` si la respuesta no lo informa."""

    conversation_id: int
    can_reply: bool | None


def _unexpected(key: str) -> MessagingUnavailableError:
    return MessagingUnavailableError(f"Respuesta inesperada de Chatwoot: falta '{key}'")


def _require(mapping: Any, key: str) -> Any:
    if not isinstance(mapping, Mapping) or key not in mapping:
        raise _unexpected(key)
    return mapping[key]


def _require_int(mapping: Any, key: str) -> int:
    value = _require(mapping, key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise _unexpected(key)
    return value


def _require_list(mapping: Any, key: str) -> Sequence[Mapping[str, Any]]:
    value = _require(mapping, key)
    if not isinstance(value, list) or not all(isinstance(entry, Mapping) for entry in value):
        raise _unexpected(key)
    return value


def instant(created_at: int | float | str | None, message_id: int) -> datetime:
    """Convierte la hora de Chatwoot en un `datetime` UTC con desempate por id.

    Chatwoot informa segundos enteros (o texto ISO 8601 en los webhooks). Dos mensajes del mismo
    segundo recibirían la misma hora y un cursor `before` exclusivo saltaría uno; los
    microsegundos llevan `message_id` para dar un orden estricto.
    """

    if created_at is None or isinstance(created_at, bool):
        raise _unexpected(CREATED_AT_KEY)
    try:
        if isinstance(created_at, str):
            moment = _parse_text_time(created_at)
        else:
            moment = datetime.fromtimestamp(int(created_at), UTC)
    except (ValueError, OverflowError, OSError):
        raise _unexpected(CREATED_AT_KEY) from None
    return moment.replace(microsecond=0) + timedelta(
        microseconds=message_id % _MICROSECONDS_PER_SECOND
    )


def _parse_text_time(text: str) -> datetime:
    if text.isdigit():
        return datetime.fromtimestamp(int(text), UTC)
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def decode_direction(message_type: Any) -> MessageDirection | None:
    """Dirección del mensaje; `None` para actividad, plantillas y valores desconocidos.

    Chatwoot usa enteros en la API y texto en los webhooks, así que se aceptan ambos.
    """

    try:
        return _DIRECTIONS.get(message_type)
    except TypeError:
        return None


def decode_listed_direction(message_type: Any) -> MessageDirection | None:
    """Como `decode_direction`, pero la actividad (`2`) es un mensaje del sistema, no `None`."""

    try:
        return _LISTED_DIRECTIONS.get(message_type)
    except TypeError:
        return None


# --- Contactos ----------------------------------------------------------------------------


def _digits(raw: str) -> str:
    return _NON_DIGITS.sub("", raw)


def build_contact_search_params(phone: PhoneNumber) -> dict[str, str]:
    return {SEARCH_QUERY_PARAM: phone.digits}


def build_contact_request(inbox_id: int, phone: PhoneNumber) -> dict[str, Any]:
    return {INBOX_ID_KEY: inbox_id, NAME_KEY: phone.value, PHONE_NUMBER_KEY: phone.value}


def find_contact_id(search_body: Any, phone: PhoneNumber) -> int | None:
    """Id del contacto cuyo teléfono coincide exactamente.

    La búsqueda de Chatwoot es por subcadena (`ILIKE %q%`), así que un resultado más largo o más
    corto que el número pedido no sirve.
    """

    wanted = phone.digits
    for contact in _require_list(search_body, PAYLOAD_KEY):
        raw = contact.get(PHONE_NUMBER_KEY)
        if isinstance(raw, str) and _digits(raw) == wanted:
            return _require_int(contact, ID_KEY)
    return None


def parse_contact_id(created_body: Any) -> int:
    contact = _require(_require(created_body, PAYLOAD_KEY), CONTACT_KEY)
    return _require_int(contact, ID_KEY)


# --- Conversaciones -----------------------------------------------------------------------


def build_conversation_request(inbox_id: int, contact_id: int) -> dict[str, Any]:
    """Sin `status`: una conversación existente podría estar tomada por un encargado."""

    return {INBOX_ID_KEY: inbox_id, CONTACT_ID_KEY: contact_id}


def parse_conversation_ref(body: Any) -> ConversationRef:
    can_reply = body.get(CAN_REPLY_KEY) if isinstance(body, Mapping) else None
    return ConversationRef(
        conversation_id=_require_int(body, ID_KEY),
        can_reply=can_reply if isinstance(can_reply, bool) else None,
    )


def build_status_request(status: ConversationStatus) -> dict[str, str]:
    """Cambio de estado: el bot atiende `pending` y un encargado `open`."""

    return {STATUS_KEY: _CHATWOOT_STATUSES[status]}


def build_conversation_list_params(
    inbox_id: int, status: ConversationStatus | None, page: int, *, include_resolved: bool = False
) -> dict[str, str | int]:
    """Parámetros del listado.

    Sin filtro, o con resueltas incluidas (cuentan como ``BOT``), se piden todas y el filtro se
    aplica al leer; las pospuestas siempre se descartan.
    """

    return {
        INBOX_ID_KEY: inbox_id,
        STATUS_KEY: (
            STATUS_ALL if status is None or include_resolved else _CHATWOOT_STATUSES[status]
        ),
        PAGE_PARAM: page,
        SORT_BY_PARAM: SORT_LAST_ACTIVITY_DESC,
    }


def conversation_items(list_body: Any) -> Sequence[Mapping[str, Any]]:
    return _require_list(_require(list_body, DATA_KEY), PAYLOAD_KEY)


def parse_conversation_summary(
    item: Mapping[str, Any], *, include_resolved: bool = False
) -> ConversationSummary | None:
    """Resumen de una conversación, o `None` si no es listable o no tiene teléfono.

    Son listables las pendientes y abiertas, y las resueltas solo con `include_resolved`.
    """

    lifecycle = _LIFECYCLES.get(str(item.get(STATUS_KEY)))
    phone = _sender_phone(item)
    if lifecycle is None or phone is None:
        return None
    if lifecycle is ConversationLifecycle.RESOLVED and not include_resolved:
        return None
    last = item.get(LAST_NON_ACTIVITY_KEY)
    unread = item.get(UNREAD_COUNT_KEY)
    return ConversationSummary(
        conversation_id=_require_int(item, ID_KEY),
        phone=phone,
        status=(
            ConversationStatus.HUMAN
            if lifecycle is ConversationLifecycle.OPEN
            else ConversationStatus.BOT
        ),
        service_window_open=item.get(CAN_REPLY_KEY) is True,
        last_message_at=_last_message_at(item),
        lifecycle=lifecycle,
        contact_name=_meta_name(item, SENDER_KEY),
        unread_count=unread if isinstance(unread, int) and not isinstance(unread, bool) else 0,
        last_message_preview=_preview(last) if isinstance(last, Mapping) else None,
        assignee_name=_meta_name(item, ASSIGNEE_KEY),
    )


def has_listable_status(item: Mapping[str, Any], *, include_resolved: bool = False) -> bool:
    """Indica si la conversación se lista: pendiente o abierta, y resuelta si se pide."""

    lifecycle = _LIFECYCLES.get(str(item.get(STATUS_KEY)))
    if lifecycle is None:
        return False
    return include_resolved or lifecycle is not ConversationLifecycle.RESOLVED


def _meta_name(item: Mapping[str, Any], key: str) -> str | None:
    meta = item.get(META_KEY)
    person = meta.get(key) if isinstance(meta, Mapping) else None
    name = person.get(NAME_KEY) if isinstance(person, Mapping) else None
    return name if isinstance(name, str) and name else None


def _preview(message: Mapping[str, Any]) -> str | None:
    """Vista previa del último mensaje que no es actividad: texto o «[Adjunto]»."""

    content = message.get(CONTENT_KEY)
    if isinstance(content, str) and content.strip():
        return content.strip()[:PREVIEW_MAX_CHARS]
    attachments = message.get(ATTACHMENTS_KEY)
    return ATTACHMENT_PREVIEW if isinstance(attachments, list) and attachments else None


def conversation_status_of(status: Any) -> ConversationStatus | None:
    """Quién atiende según el estado de Chatwoot; `None` si no es `pending` ni `open`."""

    try:
        return _CONVERSATION_STATUSES.get(status)
    except TypeError:
        return None


def incoming_sender_phone(body: Mapping[str, Any]) -> PhoneNumber | None:
    """Teléfono del contacto que escribió: `sender` del mensaje o, si falta, `meta.sender`."""

    candidates: list[Any] = [body.get(SENDER_KEY)]
    conversation = body.get(CONVERSATION_KEY)
    if isinstance(conversation, Mapping):
        meta = conversation.get(META_KEY)
        candidates.append(meta.get(SENDER_KEY) if isinstance(meta, Mapping) else None)
    for sender in candidates:
        raw = sender.get(PHONE_NUMBER_KEY) if isinstance(sender, Mapping) else None
        if isinstance(raw, str):
            try:
                return PhoneNumber.parse(raw)
            except ValidationError:
                continue
    return None


def _sender_phone(item: Mapping[str, Any]) -> PhoneNumber | None:
    meta = item.get(META_KEY)
    sender = meta.get(SENDER_KEY) if isinstance(meta, Mapping) else None
    raw = sender.get(PHONE_NUMBER_KEY) if isinstance(sender, Mapping) else None
    if not isinstance(raw, str):
        return None
    try:
        return PhoneNumber.parse(raw)
    except ValidationError:
        return None


def _last_message_at(item: Mapping[str, Any]) -> datetime | None:
    """Hora del último mensaje que no es actividad; el aviso de reapertura no la mueve."""

    last = item.get(LAST_NON_ACTIVITY_KEY)
    if isinstance(last, Mapping):
        return instant(_require(last, CREATED_AT_KEY), _require_int(last, ID_KEY))
    messages = item.get(MESSAGES_KEY)
    if isinstance(messages, list) and messages:
        last = messages[-1]
        return instant(_require(last, CREATED_AT_KEY), _require_int(last, ID_KEY))
    activity = item.get(LAST_ACTIVITY_AT_KEY)
    return instant(activity, 0) if activity is not None else None


# --- Mensajes: envío ----------------------------------------------------------------------


def build_text_message(content: str) -> dict[str, Any]:
    return {CONTENT_KEY: content, MESSAGE_TYPE_KEY: OUTGOING_MESSAGE_TYPE, PRIVATE_KEY: False}


def flatten_sections(sections: Sequence[ListSection]) -> list[dict[str, str]]:
    """Filas de todas las secciones, en orden.

    Chatwoot construye el mensaje interactivo solo con `items`: se pierden los títulos de sección
    y las descripciones de fila.
    """

    return [
        {ITEM_TITLE_KEY: row.title, ITEM_VALUE_KEY: row.id}
        for section in sections
        for row in section.rows
    ]


def build_list_message(body: str, sections: Sequence[ListSection]) -> dict[str, Any]:
    return {
        **build_text_message(body),
        CONTENT_TYPE_KEY: INPUT_SELECT_CONTENT_TYPE,
        CONTENT_ATTRIBUTES_KEY: {ITEMS_KEY: flatten_sections(sections)},
    }


def build_template_params(
    name: str, params: Mapping[str, str], *, category: str, language: str
) -> dict[str, Any]:
    """Solo parámetros del cuerpo; los botones de la plantilla no están soportados."""

    return {
        NAME_KEY: name,
        CATEGORY_KEY: category,
        LANGUAGE_KEY: language,
        PROCESSED_PARAMS_KEY: {BODY_PARAMS_KEY: dict(params)},
    }


def build_template_message(
    name: str, params: Mapping[str, str], *, category: str, language: str
) -> dict[str, Any]:
    return {
        **build_text_message(TEMPLATE_PLACEHOLDER.format(name=name)),
        TEMPLATE_PARAMS_KEY: build_template_params(
            name, params, category=category, language=language
        ),
    }


def build_attachment_form(caption: str | None) -> dict[str, str]:
    form = {MESSAGE_TYPE_KEY: OUTGOING_MESSAGE_TYPE}
    if caption is not None:
        form[CONTENT_KEY] = caption
    return form


def build_attachment_files(
    filename: str, data: bytes, content_type: str
) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [(ATTACHMENT_FILE_FIELD, (filename, data, content_type))]


# --- Mensajes: respuestas -----------------------------------------------------------------


def parse_message_receipt(body: Any) -> MessageReceipt:
    """Recibo del envío; el id es el de Chatwoot, nunca el WAMID (`source_id`)."""

    message_id = _require_int(body, ID_KEY)
    return MessageReceipt(
        message_id=str(message_id),
        conversation_id=_require_int(body, CONVERSATION_ID_KEY),
        sent_at=instant(_require(body, CREATED_AT_KEY), message_id),
    )


def build_message_list_params(before_id: int | None) -> dict[str, int]:
    """Cursor por id: `before` es exclusivo y Chatwoot devuelve los 20 mensajes anteriores."""

    return {} if before_id is None else {BEFORE_PARAM: before_id}


def message_items(list_body: Any) -> Sequence[Mapping[str, Any]]:
    return _require_list(list_body, PAYLOAD_KEY)


def oldest_message_id(items: Sequence[Mapping[str, Any]]) -> int:
    """Id menor de una página: es el cursor `before` de la página anterior."""

    return min(_require_int(item, ID_KEY) for item in items)


def parse_conversation_message(item: Mapping[str, Any]) -> ConversationMessage | None:
    """Mensaje, aviso de actividad incluido; `None` para plantillas y notas privadas.

    El remitente es el tipo crudo de Chatwoot: la autoría real (bot o encargado) la resuelve el
    *outbox* (D3). Un aviso de actividad nunca trae remitente.
    """

    direction = decode_listed_direction(item.get(MESSAGE_TYPE_KEY))
    if direction is None or item.get(PRIVATE_KEY) is True:
        return None
    message_id = _require_int(item, ID_KEY)
    content = item.get(CONTENT_KEY)
    sender = None if direction is MessageDirection.ACTIVITY else item.get(SENDER_KEY)
    sender_type = sender.get(TYPE_KEY) if isinstance(sender, Mapping) else None
    sender_name = sender.get(NAME_KEY) if isinstance(sender, Mapping) else None
    status = item.get(STATUS_KEY)
    content_type = item.get(CONTENT_TYPE_KEY)
    return ConversationMessage(
        message_id=str(message_id),
        conversation_id=_require_int(item, CONVERSATION_ID_KEY),
        direction=direction,
        body=content if isinstance(content, str) else None,
        sent_at=instant(_require(item, CREATED_AT_KEY), message_id),
        attachment_filename=_attachment_filename(item),
        sender=_SENDERS.get(sender_type) if isinstance(sender_type, str) else None,
        sender_name=sender_name if isinstance(sender_name, str) and sender_name else None,
        status=status if isinstance(status, str) else None,
        external_error=external_error(item),
        content_type=content_type if isinstance(content_type, str) else None,
        attachments=tuple(attachments_of(item)),
    )


def attachments_of(item: Mapping[str, Any]) -> Iterator[MessageAttachment]:
    """Adjuntos de un mensaje; se omiten las entradas sin `id` entero."""

    for _, attachment in _raw_attachments(item):
        yield attachment


def find_attachment(
    items: Sequence[Mapping[str, Any]], attachment_id: int
) -> tuple[MessageAttachment, str] | None:
    """Adjunto y URL pública (`data_url`) con ese id entre mensajes públicos, si está."""

    for item in items:
        if item.get(PRIVATE_KEY) is True:
            continue
        for url, attachment in _raw_attachments(item):
            if attachment.attachment_id == attachment_id and url is not None:
                return attachment, url
    return None


def _raw_attachments(item: Mapping[str, Any]) -> Iterator[tuple[str | None, MessageAttachment]]:
    entries = item.get(ATTACHMENTS_KEY)
    if not isinstance(entries, list):
        return
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        attachment_id = entry.get(ID_KEY)
        if isinstance(attachment_id, bool) or not isinstance(attachment_id, int):
            continue
        url = entry.get(DATA_URL_KEY)
        url = url if isinstance(url, str) else None
        yield (
            url,
            MessageAttachment(
                attachment_id=attachment_id,
                file_type=_text(entry.get(FILE_TYPE_KEY)) or "file",
                content_type=_text(entry.get(CONTENT_TYPE_KEY)),
                extension=_text(entry.get(EXTENSION_KEY)),
                file_size=_whole(entry.get(FILE_SIZE_KEY)),
                filename=_filename_of(url),
            ),
        )


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _whole(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _filename_of(url: str | None) -> str | None:
    if url is None:
        return None
    return unquote(urlsplit(url).path.rsplit("/", 1)[-1]) or None


def _attachment_filename(item: Mapping[str, Any]) -> str | None:
    attachments = item.get(ATTACHMENTS_KEY)
    if not isinstance(attachments, list) or not attachments:
        return None
    url = attachments[0].get(DATA_URL_KEY) if isinstance(attachments[0], Mapping) else None
    return _filename_of(url if isinstance(url, str) else None)


# --- Webhooks y estado de entrega ---------------------------------------------------------


def delivery_status_from(value: Any) -> DeliveryStatus | None:
    """Estado de entrega que se registra, o `None` para `sent` y cualquier valor desconocido."""

    return _DELIVERY_STATUSES.get(value) if isinstance(value, str) else None


def embedded_message(body: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Mensaje del evento tal como Chatwoot lo incrusta en `conversation.messages`.

    En los webhooks de mensaje el cuerpo no trae `status` ni la hora de actualización del mensaje:
    solo los lleva la copia incrustada en la conversación. Se busca por id, no por posición, y si
    no está no se confía en ninguna otra entrada.
    """

    message_id = body.get(ID_KEY)
    conversation = body.get(CONVERSATION_KEY)
    messages = conversation.get(MESSAGES_KEY) if isinstance(conversation, Mapping) else None
    if isinstance(message_id, bool) or not isinstance(messages, list):
        return None
    for message in messages:
        if isinstance(message, Mapping) and message.get(ID_KEY) == message_id:
            return message
    return None


def external_error(message: Mapping[str, Any]) -> str | None:
    """Motivo del rechazo (`content_attributes.external_error`), si el mensaje lo trae."""

    attributes = message.get(CONTENT_ATTRIBUTES_KEY)
    reason = attributes.get(EXTERNAL_ERROR_KEY) if isinstance(attributes, Mapping) else None
    return reason if isinstance(reason, str) and reason else None


def event_time(value: Any) -> datetime | None:
    """Hora de actualización de un evento en UTC, o `None` si falta o no se puede leer.

    A diferencia de `instant`, no suma el desempate por id: es la hora real del evento.
    """

    if not isinstance(value, str | int | float) or isinstance(value, bool):
        return None
    try:
        if isinstance(value, str):
            return _parse_text_time(value)
        return datetime.fromtimestamp(int(value), UTC)
    except (ValueError, OverflowError, OSError):
        return None
