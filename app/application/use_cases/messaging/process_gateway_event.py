"""Caso de uso ProcessGatewayEvent: punto de enrutamiento de los eventos del gateway.

Hoy solo los avisos de entrega cambian datos; el resto se registra y se da por recibido. Los
logs llevan identificadores y estados, nunca contenido de mensajes, nombres ni teléfonos.
"""

from datetime import UTC, datetime

from app.application.dtos.gateway_event_dto import (
    DeliveryNotice,
    GatewayEventOutcome,
    UnhandledGatewayEvent,
)
from app.application.ports.output.gateway_event_port import IGatewayEventPort
from app.application.ports.output.outbox_repository_port import OutboxTransactionFactory
from app.application.use_cases.messaging.record_delivery_status import RecordDeliveryStatus
from app.core.logging import get_logger
from app.domain.exceptions.outbox_exceptions import InvalidOutboxStateError
from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.outbox import DeliveryStatus


class ProcessGatewayEvent:
    """Interpreta un evento y, si es un aviso de entrega, lo registra en su propia transacción."""

    def __init__(
        self, *, transaction: OutboxTransactionFactory, gateway: IGatewayEventPort
    ) -> None:
        self._transaction = transaction
        self._gateway = gateway

    async def execute(
        self, *, raw_body: bytes, received_at: datetime, last_attempt: bool = False
    ) -> GatewayEventOutcome:
        """Procesa el cuerpo crudo del webhook.

        ``received_at`` es la hora firmada del webhook y sirve de ``at`` cuando el aviso no trae
        la suya. ``last_attempt`` indica que el trabajo no se reintentará más: un mensaje que
        sigue desconocido se registra entonces como aviso sin pareja.
        """

        # Los loggers se crean en cada llamada: structlog cachea el primero tras configurarse.
        log = get_logger("gateway_events")
        try:
            event = self._gateway.parse_event(raw_body)
        except ValidationError:
            log.warning("gateway_event_malformed")
            return GatewayEventOutcome.MALFORMED
        if isinstance(event, UnhandledGatewayEvent):
            log.info(
                "gateway_event_unhandled",
                kind=event.kind,
                direction=event.direction.value if event.direction else None,
                conversation_id=event.conversation_id,
                external_message_id=event.external_message_id,
            )
            return GatewayEventOutcome.UNHANDLED
        return await self._process_notice(event, received_at, last_attempt=last_attempt)

    async def _process_notice(
        self, notice: DeliveryNotice, received_at: datetime, *, last_attempt: bool
    ) -> GatewayEventOutcome:
        log = get_logger("gateway_events")
        async with self._transaction() as repository:
            known = await repository.get_by_external_id(notice.external_message_id) is not None
        if not known:
            if last_attempt:
                log.warning(
                    "delivery_notice_unmatched",
                    external_message_id=notice.external_message_id,
                    delivery_status=notice.status.value if notice.status else None,
                )
            return GatewayEventOutcome.UNKNOWN_MESSAGE

        status, error = notice.status, notice.error
        if status is None and not notice.status_in_payload and notice.conversation_id is not None:
            # La consulta a la API va fuera de toda transacción para no retener una conexión.
            report = await self._gateway.get_delivery_status(
                notice.conversation_id, notice.external_message_id
            )
            if report is not None:
                status, error = report.status, notice.error or report.error
        if status is None:
            log.debug("delivery_notice_unresolved", external_message_id=notice.external_message_id)
            return GatewayEventOutcome.UNRESOLVED

        at = _as_utc(notice.updated_at or received_at)
        async with self._transaction() as repository:
            try:
                applied = await RecordDeliveryStatus(repository).execute(
                    external_message_id=notice.external_message_id,
                    status=status,
                    error=error if status is DeliveryStatus.FAILED else None,
                    at=at,
                )
            except InvalidOutboxStateError:
                log.warning(
                    "delivery_notice_invalid_state",
                    external_message_id=notice.external_message_id,
                    delivery_status=status.value,
                )
                return GatewayEventOutcome.IGNORED
        return GatewayEventOutcome.APPLIED if applied else GatewayEventOutcome.IGNORED


def _as_utc(moment: datetime) -> datetime:
    """Hora con zona UTC; una hora sin zona se interpreta como UTC."""

    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)
