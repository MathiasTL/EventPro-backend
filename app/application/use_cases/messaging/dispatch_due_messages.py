"""Caso de uso DispatchDueMessages: reserva y entrega los mensajes salientes vencidos.

Garantía de entrega al menos una vez. El ciclo usa tres tipos de transacción, todas cortas:
una para reservar el lote (``claim_due``), ninguna durante el envío y una por mensaje para
guardar su resultado. Si el worker muere después de que Chatwoot aceptó el mensaje y antes de
guardarlo, la reserva vence y el mensaje se envía de nuevo: se prefiere un duplicado a una
pérdida.
"""

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from typing import Any

from app.application.dtos.messaging_dto import ListRow, ListSection, MessageReceipt
from app.application.ports.output.clock_port import IClockPort
from app.application.ports.output.document_source_port import IDocumentSourcePort
from app.application.ports.output.messaging_port import IMessagingPort
from app.application.ports.output.outbox_repository_port import OutboxTransactionFactory
from app.core.logging import get_logger
from app.domain.entities.outbox_message import OutboxMessage
from app.domain.exceptions.messaging_exceptions import (
    MessagingUnavailableError,
    ServiceWindowClosedError,
)
from app.domain.exceptions.resource_exceptions import DomainError, ValidationError
from app.domain.value_objects.outbox import MessageType, OutboxStatus


@dataclass(frozen=True)
class DispatchSummary:
    """Resultado de un ciclo, para el log del worker y las pruebas."""

    claimed: int = 0
    sent: int = 0
    rescheduled: int = 0
    failed: int = 0
    discarded: int = 0
    errors: int = 0


class _Outcome(StrEnum):
    SENT = "sent"
    RESCHEDULED = "rescheduled"
    FAILED = "failed"
    DISCARDED = "discarded"
    ERROR = "error"


@dataclass(frozen=True)
class _Delivered:
    receipt: MessageReceipt


@dataclass(frozen=True)
class _Rejected:
    """``error`` es lo que se guarda en ``last_error``: nunca incluye el contenido."""

    error: str
    error_type: str
    permanent: bool


def _logger() -> Any:
    # El logger se crea en cada llamada: structlog cachea el primero tras configurarse.
    return get_logger("outbox")


def _sections(raw: list[dict[str, Any]]) -> tuple[ListSection, ...]:
    return tuple(
        ListSection(
            title=section["title"],
            rows=tuple(
                ListRow(id=row["id"], title=row["title"], description=row.get("description"))
                for row in section["rows"]
            ),
        )
        for section in raw
    )


class DispatchDueMessages:
    def __init__(
        self,
        *,
        transaction: OutboxTransactionFactory,
        messaging: IMessagingPort,
        documents: IDocumentSourcePort,
        clock: IClockPort,
        batch_size: int,
        lease_seconds: int,
    ) -> None:
        if batch_size < 1 or lease_seconds < 1:
            raise ValidationError("batch_size y lease_seconds deben ser mayores que cero")
        self._transaction = transaction
        self._messaging = messaging
        self._documents = documents
        self._clock = clock
        self._batch_size = batch_size
        self._lease = timedelta(seconds=lease_seconds)

    async def execute(self) -> DispatchSummary:
        """Entrega un lote. Un error al reservar aborta el ciclo; el siguiente lo reintenta."""

        async with self._transaction() as repository:
            claimed = list(
                await repository.claim_due(
                    now=self._clock.utcnow(), limit=self._batch_size, lease=self._lease
                )
            )
        outcomes: list[_Outcome] = []
        for message in claimed:
            try:
                outcomes.append(await self._dispatch(message))
            except Exception as exc:
                # El fallo de un mensaje no afecta a los demás; su reserva vencerá sola.
                _logger().error(
                    "outbox_result_not_saved",
                    message_id=str(message.id),
                    error_type=type(exc).__name__,
                )
                outcomes.append(_Outcome.ERROR)
        return DispatchSummary(
            claimed=len(claimed),
            sent=outcomes.count(_Outcome.SENT),
            rescheduled=outcomes.count(_Outcome.RESCHEDULED),
            failed=outcomes.count(_Outcome.FAILED),
            discarded=outcomes.count(_Outcome.DISCARDED),
            errors=outcomes.count(_Outcome.ERROR),
        )

    async def _dispatch(self, message: OutboxMessage) -> _Outcome:
        result = await self._send(message)
        async with self._transaction() as repository:
            current = await repository.get_by_id(message.id, for_update=True)
            if current is None or current.status is not OutboxStatus.PENDING:
                # La reserva venció y otro worker ya resolvió el mensaje: no se pisa su resultado.
                _logger().warning(
                    "outbox_result_discarded",
                    message_id=str(message.id),
                    current_status=current.status.value if current else None,
                )
                return _Outcome.DISCARDED
            now = self._clock.utcnow()
            if isinstance(result, _Delivered):
                current.mark_sent(
                    external_message_id=result.receipt.message_id,
                    conversation_id=result.receipt.conversation_id,
                    now=now,
                )
                await repository.save(current)
                _logger().info(
                    "outbox_message_sent",
                    message_id=str(current.id),
                    message_type=current.message_type.value,
                )
                return _Outcome.SENT
            status = current.register_failure(
                error=result.error, permanent=result.permanent, now=now
            )
            await repository.save(current)
            outcome = _Outcome.FAILED if status is OutboxStatus.FAILED else _Outcome.RESCHEDULED
            _logger().warning(
                f"outbox_message_{outcome.value}",
                message_id=str(current.id),
                message_type=current.message_type.value,
                attempts=current.attempts,
                error_type=result.error_type,
                permanent=result.permanent,
            )
            return outcome

    async def _send(self, message: OutboxMessage) -> _Delivered | _Rejected:
        """Llama al gateway fuera de toda transacción y clasifica el error."""

        if message.payload is None:
            return _Rejected(
                "El mensaje no tiene contenido para enviar", "MissingPayload", permanent=True
            )
        try:
            return _Delivered(await self._deliver(message, message.payload))
        except ServiceWindowClosedError as exc:
            return _Rejected(f"{type(exc).__name__}: {exc}", type(exc).__name__, permanent=True)
        except MessagingUnavailableError as exc:
            return _Rejected(f"{type(exc).__name__}: {exc}", type(exc).__name__, permanent=False)
        except DomainError as exc:
            # Los mensajes de dominio son textos fijos del sistema; se conservan para diagnóstico.
            return _Rejected(f"{type(exc).__name__}: {exc}", type(exc).__name__, permanent=False)
        except Exception as exc:
            # Otro error: transitorio. Solo se guarda el tipo, porque su texto podría repetir
            # el contenido del mensaje (por ejemplo, un OTP).
            return _Rejected(type(exc).__name__, type(exc).__name__, permanent=False)

    async def _deliver(self, message: OutboxMessage, payload: dict[str, Any]) -> MessageReceipt:
        to = message.recipient
        if message.message_type is MessageType.TEXT:
            return await self._messaging.send_text(to, payload["body"])
        if message.message_type is MessageType.TEMPLATE:
            return await self._messaging.send_template(to, payload["name"], payload["params"])
        if message.message_type is MessageType.INTERACTIVE:
            return await self._messaging.send_interactive_list(
                to, payload["body"], _sections(payload["sections"])
            )
        data = await self._documents.read(payload["path"])
        return await self._messaging.send_attachment(
            to, data, payload["filename"], payload["content_type"], payload.get("caption")
        )
