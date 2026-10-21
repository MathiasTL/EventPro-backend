"""Router HTTP de la bandeja de conversaciones (spec 09).

``/conversations/stream`` se declara antes que cualquier ruta ``/conversations/{id}`` y el
``{id}`` es un entero, para que el literal no se interprete como identificador.

Los errores del gateway se traducen solo aquí (D10): un manejador global alteraría otros módulos.
"""

import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, Any
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse
from pydantic import ValidationError as PydanticValidationError
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.application.dtos.inbox_dto import (
    SEARCH_MIN_CHARS,
    AssignedFilter,
    ConversationFilters,
)
from app.application.dtos.messaging_dto import ConversationStatus
from app.application.ports.output.conversation_event_subscriber_port import (
    IConversationEventSubscriberPort,
)
from app.application.ports.output.payment_evidence_storage_port import IPaymentEvidenceStoragePort
from app.application.use_cases.messaging.conversation_assignment import (
    ReleaseConversation,
    TakeoverConversation,
)
from app.application.use_cases.messaging.get_conversation_attachment import (
    GetConversationAttachment,
)
from app.application.use_cases.messaging.list_conversation_messages import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    ListConversationMessages,
)
from app.application.use_cases.messaging.list_conversations import (
    GetConversation,
    ListConversations,
)
from app.application.use_cases.messaging.mark_conversation_read import MarkConversationRead
from app.application.use_cases.messaging.mark_event_done import MarkEventDone
from app.application.use_cases.messaging.send_conversation_message import (
    QueuedMessage,
    RetryConversationMessage,
    SendConversationMessage,
)
from app.domain.exceptions.messaging_exceptions import (
    ConversationNotTakenError,
    ConversationTakenByOtherError,
    ConversationWindowClosedError,
    InvalidLeadTransitionError,
    MessagingUnavailableError,
    ServiceWindowClosedError,
)
from app.domain.exceptions.outbox_exceptions import (
    InvalidOutboxStateError,
    OutboxMessageNotFoundError,
)
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError, ValidationError
from app.domain.exceptions.storage_exceptions import EvidenceValidationError
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.primary.web.deps import (
    AuthContext,
    StreamAuthContext,
    get_stream_auth_context,
    require_role,
)
from app.infrastructure.adapters.primary.web.problem import ProblemError
from app.infrastructure.adapters.primary.web.schemas.conversation_schemas import (
    ConversationPageResponse,
    ConversationResponse,
    MessagePageResponse,
    QueuedMessageResponse,
    SendMessageRequest,
)
from app.infrastructure.adapters.primary.web.sse import event_stream
from app.infrastructure.adapters.secondary.storage.local_evidence_storage import mime_for_path
from app.infrastructure.di import containers

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["Conversaciones"])

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
GATEWAY_UNAVAILABLE_DETAIL = "La mensajería no está disponible temporalmente."
_NOT_FOUND_DETAIL = "La conversación no existe."

InboxUser = Annotated[AuthContext, Depends(require_role(Role.ENCARGADO, Role.SUPERADMIN))]
ConversationId = Annotated[int, Path(ge=1)]
AttachmentId = Annotated[int, Path(ge=1)]

ATTACHMENT_FIELD = "attachment"
_MULTIPART = "multipart/form-data"
_MAX_FORM_FIELDS = 4
_MAX_PART_BYTES = 64 * 1024
_MULTIPART_OVERHEAD = 64 * 1024
_UNSAFE_FILENAME_CHARS = re.compile(r'[\x00-\x1f\x7f"\\/]')


@contextmanager
def _gateway_errors() -> Iterator[None]:
    """``MessagingUnavailableError`` es 503 y ``ResourceNotFoundError`` es 404, con detalle fijo."""

    try:
        yield
    except MessagingUnavailableError as exc:
        raise ProblemError(
            503,
            "messaging-gateway-unavailable",
            "Servicio no disponible",
            GATEWAY_UNAVAILABLE_DETAIL,
        ) from exc
    except ResourceNotFoundError as exc:
        raise ProblemError(404, "not-found", "No encontrado", _NOT_FOUND_DETAIL) from exc


@router.get("/stream", response_class=StreamingResponse)
async def stream_conversation_events(
    request: Request,
    auth: Annotated[StreamAuthContext, Depends(get_stream_auth_context)],
    subscriber: Annotated[
        IConversationEventSubscriberPort, Depends(containers.get_conversation_event_subscriber)
    ],
) -> StreamingResponse:
    """Eventos de la bandeja en tiempo real (SSE); la autenticación ocurre antes del stream."""
    return StreamingResponse(
        event_stream(
            subscriber,
            expires_at=auth.expires_at,
            is_disconnected=request.is_disconnected,
        ),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get("", response_model=ConversationPageResponse)
async def list_conversations(
    context: InboxUser,
    use_case: Annotated[ListConversations, Depends(containers.get_list_conversations_use_case)],
    mode: Annotated[ConversationStatus | None, Query()] = None,
    assigned: Annotated[AssignedFilter | None, Query()] = None,
    assigned_user_id: Annotated[UUID | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    include_resolved: Annotated[bool, Query()] = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ConversationPageResponse:
    """Bandeja ordenada por ``last_message_at`` descendente (4.1, 7.2)."""

    if assigned_user_id is not None and context.role is not Role.SUPERADMIN:
        raise ProblemError(
            403, "forbidden", "Prohibido", "Solo un SUPERADMIN puede filtrar por encargado."
        )
    query = q.strip() if q is not None else None
    if query is not None and len(query) < SEARCH_MIN_CHARS:
        raise ProblemError(
            422,
            "validation-error",
            "Error de validación",
            f"La búsqueda requiere al menos {SEARCH_MIN_CHARS} caracteres.",
        )
    filters = ConversationFilters(
        mode=mode,
        assigned=assigned,
        assigned_user_id=assigned_user_id,
        q=query,
        include_resolved=include_resolved,
        page=page,
        page_size=page_size,
    )
    with _gateway_errors():
        result = await use_case.execute(filters, user_id=context.user_id)
    return ConversationPageResponse.from_page(result)


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: ConversationId,
    context: InboxUser,
    use_case: Annotated[GetConversation, Depends(containers.get_get_conversation_use_case)],
) -> ConversationResponse:
    with _gateway_errors():
        view = await use_case.execute(conversation_id)
    return ConversationResponse.from_view(view)


@router.get(
    "/{conversation_id}/messages",
    response_model=MessagePageResponse,
    response_model_exclude_unset=True,
)
async def list_conversation_messages(
    conversation_id: ConversationId,
    context: InboxUser,
    use_case: Annotated[
        ListConversationMessages, Depends(containers.get_list_conversation_messages_use_case)
    ],
    before: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> MessagePageResponse:
    """Del más reciente al más antiguo; ``unsent`` solo sin ``before`` (7.3)."""

    with _gateway_errors():
        page = await use_case.execute(conversation_id, before_id=before, limit=limit)
    return MessagePageResponse.from_page(conversation_id, page)


def _safe_filename(raw: str | None, default: str) -> str:
    """Sin separadores de ruta, comillas ni caracteres de control; acotado a 120 caracteres."""

    name = _UNSAFE_FILENAME_CHARS.sub("_", (raw or "").replace("\\", "/").rsplit("/", 1)[-1])
    return name.strip(" .")[:120] or default


def _content_disposition(filename: str) -> str:
    ascii_name = filename.encode("ascii", "replace").decode().replace("?", "_")
    return f"inline; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename, safe='')}"


@router.get("/{conversation_id}/attachments/{attachment_id}", response_class=Response)
async def get_conversation_attachment(
    conversation_id: ConversationId,
    attachment_id: AttachmentId,
    context: InboxUser,
    use_case: Annotated[
        GetConversationAttachment, Depends(containers.get_get_conversation_attachment_use_case)
    ],
) -> Response:
    """Proxy de medios (11, D17): el navegador nunca ve la URL de Chatwoot."""

    with _gateway_errors():
        attachment = await use_case.execute(conversation_id, attachment_id)
    filename = _safe_filename(attachment.filename, f"adjunto-{attachment_id}")
    return Response(
        content=attachment.data,
        media_type=attachment.content_type,
        headers={
            "Content-Disposition": _content_disposition(filename),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            # Un medio ajeno nunca debe ejecutar contenido activo en el origen de la API.
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


@router.post("/{conversation_id}/read", status_code=204)
async def mark_conversation_read(
    conversation_id: ConversationId,
    context: InboxUser,
    use_case: Annotated[
        MarkConversationRead, Depends(containers.get_mark_conversation_read_use_case)
    ],
) -> Response:
    with _gateway_errors():
        await use_case.execute(conversation_id)
    return Response(status_code=204)


@router.post("/{conversation_id}/lead/event-done", response_model=ConversationResponse)
async def mark_event_done(
    conversation_id: ConversationId,
    context: InboxUser,
    use_case: Annotated[MarkEventDone, Depends(containers.get_mark_event_done_use_case)],
) -> ConversationResponse:
    """Marca a mano «Evento realizado»; solo desde ``CONVERTED`` e idempotente (7.4, D25)."""

    try:
        with _gateway_errors():
            view = await use_case.execute(conversation_id, user_id=context.user_id)
    except InvalidLeadTransitionError as exc:
        raise ProblemError(409, exc.code, "Conflicto", str(exc)) from exc
    return ConversationResponse.from_view(view)


@contextmanager
def _assignment_conflicts() -> Iterator[None]:
    """409 de tomar y devolver (sección 10); ``taken-by-other`` incluye al asignado vigente."""

    try:
        yield
    except ConversationTakenByOtherError as exc:
        raise ProblemError(
            409,
            exc.code,
            "Conflicto",
            str(exc),
            assigned_user_id=str(exc.assigned_user_id) if exc.assigned_user_id else None,
        ) from exc
    except ConversationNotTakenError as exc:
        raise ProblemError(409, exc.code, "Conflicto", str(exc)) from exc


@router.post("/{conversation_id}/takeover", response_model=ConversationResponse)
async def takeover_conversation(
    conversation_id: ConversationId,
    context: InboxUser,
    use_case: Annotated[
        TakeoverConversation, Depends(containers.get_takeover_conversation_use_case)
    ],
) -> ConversationResponse:
    """Toma la conversación; un ``SUPERADMIN`` sobre la de otro la reasigna (6.3, 6.6)."""

    with _assignment_conflicts(), _gateway_errors():
        view = await use_case.execute(conversation_id, user_id=context.user_id, role=context.role)
    return ConversationResponse.from_view(view)


@router.post("/{conversation_id}/release", response_model=ConversationResponse)
async def release_conversation(
    conversation_id: ConversationId,
    context: InboxUser,
    use_case: Annotated[ReleaseConversation, Depends(containers.get_release_conversation_use_case)],
) -> ConversationResponse:
    """Devuelve la conversación al bot; la llama el asignado o un ``SUPERADMIN`` (6.5)."""

    with _assignment_conflicts(), _gateway_errors():
        view = await use_case.execute(conversation_id, user_id=context.user_id, role=context.role)
    return ConversationResponse.from_view(view)


def _queued(result: QueuedMessage) -> QueuedMessageResponse:
    return QueuedMessageResponse(
        outbox_id=result.outbox_id, chatwoot_conversation_id=result.chatwoot_conversation_id
    )


@contextmanager
def _outgoing_errors() -> Iterator[None]:
    """Errores de enviar y reintentar (6.4, 6.7) que no son 409 de asignación ni del gateway."""

    try:
        yield
    except OutboxMessageNotFoundError as exc:
        raise ProblemError(404, "not-found", "No encontrado", str(exc)) from exc
    except ServiceWindowClosedError as exc:
        expires_at = exc.expires_at if isinstance(exc, ConversationWindowClosedError) else None
        raise ProblemError(
            422,
            exc.code,
            "Error de validación",
            str(exc),
            service_window_expires_at=expires_at.isoformat() if expires_at else None,
        ) from exc
    except InvalidOutboxStateError as exc:
        raise ProblemError(409, exc.code, "Conflicto", str(exc)) from exc
    except ValidationError as exc:
        raise ProblemError(422, "validation-error", "Error de validación", str(exc)) from exc


_SEND_OPENAPI: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {"schema": SendMessageRequest.model_json_schema()},
            _MULTIPART: {
                "schema": {
                    "type": "object",
                    "required": [ATTACHMENT_FIELD],
                    "properties": {
                        ATTACHMENT_FIELD: {"type": "string", "format": "binary"},
                        "content": {"type": "string", "maxLength": 4096},
                    },
                }
            },
        },
    }
}


def _require_bounded_multipart(request: Request, max_upload_bytes: int) -> None:
    raw = request.headers.get("content-length", "")
    if not raw.isdigit():
        raise ProblemError(
            422,
            "validation-error",
            "Error de validación",
            "El envío con adjunto requiere el encabezado Content-Length.",
        )
    if int(raw) > max_upload_bytes + _MULTIPART_OVERHEAD:
        raise ProblemError(
            422, "invalid-file", "Archivo inválido", "El archivo no puede superar 5 MiB"
        )


async def _read_send_body(
    request: Request, max_upload_bytes: int
) -> SendMessageRequest | tuple[UploadFile, str | None]:
    """Un solo camino para JSON (texto) y multipart (adjunto); se decide por ``Content-Type``.

    El multipart se acota antes de leerlo: ``Content-Length`` obligatorio y limitado, un solo
    archivo y pocos campos, para que un cuerpo enorme no llene el disco temporal.
    """

    if not request.headers.get("content-type", "").lower().startswith(_MULTIPART):
        try:
            return SendMessageRequest.model_validate_json(await request.body())
        except PydanticValidationError as exc:
            errors = [
                {**error, "loc": ("body", *error["loc"])}
                for error in exc.errors(include_url=False, include_context=False)
            ]
            raise RequestValidationError(errors) from exc
    _require_bounded_multipart(request, max_upload_bytes)
    try:
        form = await request.form(
            max_files=1, max_fields=_MAX_FORM_FIELDS, max_part_size=_MAX_PART_BYTES
        )
    except StarletteHTTPException as exc:
        raise ProblemError(
            422, "invalid-file", "Archivo inválido", "El envío solo admite un archivo y un texto."
        ) from exc
    upload = form.get(ATTACHMENT_FIELD)
    caption = form.get("content")
    if not isinstance(upload, UploadFile):
        raise ProblemError(
            422, "validation-error", "Error de validación", "Falta el archivo adjunto."
        )
    if caption is not None and (not isinstance(caption, str) or len(caption) > 4096):
        raise ProblemError(
            422, "validation-error", "Error de validación", "El texto del adjunto no es válido."
        )
    return upload, (caption.strip() or None) if isinstance(caption, str) else None


async def _store_upload(
    upload: UploadFile, storage: IPaymentEvidenceStoragePort, caption: str | None
) -> tuple[str, dict[str, Any]]:
    """Valida (5 MB, contenido, tipos) y guarda; devuelve la ruta y el payload ``DOCUMENT``."""

    if upload.size is not None and upload.size > storage.max_bytes():
        raise ProblemError(
            422, "invalid-file", "Archivo inválido", "El archivo no puede superar 5 MiB"
        )
    data = await upload.read()
    try:
        path = await storage.store(
            data=data,
            content_type=upload.content_type or "",
            original_filename=upload.filename or "adjunto",
        )
    except EvidenceValidationError as exc:
        raise ProblemError(422, "invalid-file", "Archivo inválido", str(exc)) from exc
    document = {
        "path": path,
        "filename": _safe_filename(upload.filename, "adjunto"),
        "content_type": mime_for_path(path),
        "caption": caption,
    }
    return path, document


@router.post(
    "/{conversation_id}/messages",
    status_code=202,
    response_model=QueuedMessageResponse,
    openapi_extra=_SEND_OPENAPI,
)
async def send_conversation_message(
    conversation_id: ConversationId,
    request: Request,
    context: InboxUser,
    use_case: Annotated[
        SendConversationMessage, Depends(containers.get_send_conversation_message_use_case)
    ],
    storage: Annotated[IPaymentEvidenceStoragePort, Depends(containers.get_evidence_storage)],
) -> QueuedMessageResponse:
    """Encola un texto (JSON) o un adjunto (multipart) como el encargado asignado (6.4, D19)."""

    body = await _read_send_body(request, storage.max_bytes())
    if isinstance(body, SendMessageRequest):
        if body.template is not None:
            raise ProblemError(
                422,
                "validation-error",
                "Error de validación",
                "El envío de plantillas no está disponible en esta versión.",
            )
        with _assignment_conflicts(), _outgoing_errors(), _gateway_errors():
            result = await use_case.execute(
                conversation_id, user_id=context.user_id, content=body.content
            )
        return _queued(result)
    upload, caption = body
    path, document = await _store_upload(upload, storage, caption)
    try:
        with _assignment_conflicts(), _outgoing_errors(), _gateway_errors():
            result = await use_case.execute(
                conversation_id, user_id=context.user_id, document=document
            )
    except BaseException:
        # Las precondiciones fallaron o el envío no se encoló: no queda un archivo huérfano.
        try:
            await storage.delete(path)
        except Exception:
            logger.exception("No se pudo eliminar el adjunto de un envío rechazado.")
        raise
    return _queued(result)


@router.post(
    "/{conversation_id}/messages/{outbox_id}/retry",
    status_code=202,
    response_model=QueuedMessageResponse,
)
async def retry_conversation_message(
    conversation_id: ConversationId,
    outbox_id: UUID,
    context: InboxUser,
    use_case: Annotated[
        RetryConversationMessage, Depends(containers.get_retry_conversation_message_use_case)
    ],
) -> QueuedMessageResponse:
    """Reencola la misma fila del outbox de un mensaje fallido (6.7, D6)."""

    with _assignment_conflicts(), _outgoing_errors(), _gateway_errors():
        result = await use_case.execute(conversation_id, outbox_id, user_id=context.user_id)
    return _queued(result)
