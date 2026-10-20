"""Webhook de cuenta de Chatwoot: ``POST /webhooks/chatwoot``.

La ruta no usa JWT: la autenticación es la firma HMAC sobre los bytes crudos del cuerpo. Falla
cerrada (401) si el secreto no está configurado. No interpreta el evento: lo deduplica, lo encola
y responde; el worker decide qué hacer con él.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.application.ports.output.clock_port import IClockPort
from app.application.use_cases.messaging.errors import GatewayEventNotQueuedError
from app.application.use_cases.messaging.receive_gateway_event import ReceiveGatewayEvent
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.infrastructure.adapters.primary.web.problem import ProblemError
from app.infrastructure.adapters.primary.webhooks.chatwoot_signature import (
    SIGNATURE_PREFIX,
    SignatureCheck,
    verify_chatwoot_signature,
)
from app.infrastructure.di import containers

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

SIGNATURE_HEADER = "X-Chatwoot-Signature"
TIMESTAMP_HEADER = "X-Chatwoot-Timestamp"
DELIVERY_HEADER = "X-Chatwoot-Delivery"
# Marca que sustituye en los logs al id de un evento sin encabezado de entrega: ese id es el
# resumen de la firma y los logs nunca llevan firmas.
SIGNATURE_DIGEST_LOG_ID = "signature-digest"


class WebhookAck(BaseModel):
    status: Literal["EVENT_RECEIVED"] = "EVENT_RECEIVED"


@dataclass(frozen=True)
class VerifiedChatwootEvent:
    """Entrega verificada: id de deduplicación, cuerpo crudo e instante de la hora firmada."""

    event_id: str
    raw_body: bytes
    received_at: datetime
    has_delivery_id: bool

    @property
    def loggable_id(self) -> str:
        return self.event_id if self.has_delivery_id else SIGNATURE_DIGEST_LOG_ID


async def verified_chatwoot_event(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    clock: Annotated[IClockPort, Depends(containers.get_clock_port)],
) -> VerifiedChatwootEvent:
    """Verifica la firma antes de cualquier otro procesamiento; el cuerpo no se interpreta."""

    # Los loggers se crean en cada llamada: structlog cachea el primero tras configurarse.
    log = get_logger("chatwoot_webhook")
    raw_body = await request.body()
    timestamp = request.headers.get(TIMESTAMP_HEADER)
    signature = request.headers.get(SIGNATURE_HEADER)
    check = verify_chatwoot_signature(
        settings.chatwoot_webhook_secret.get_secret_value(),
        timestamp,
        raw_body,
        signature,
        clock.utcnow(),
    )
    if check is not SignatureCheck.VALID or timestamp is None or signature is None:
        log.warning("chatwoot_webhook_rejected", reason=check.value)
        raise ProblemError(
            401, "invalid-webhook-signature", "No autorizado", "La firma del webhook no es válida."
        )

    delivery_id = request.headers.get(DELIVERY_HEADER, "").strip()
    if not delivery_id:
        log.info("chatwoot_webhook_delivery_id_missing")
    return VerifiedChatwootEvent(
        # Sin encabezado de entrega, el resumen de la firma ya verificada identifica la entrega.
        event_id=delivery_id or signature.removeprefix(SIGNATURE_PREFIX),
        raw_body=raw_body,
        # Hora firmada del webhook: no cambia con los reintentos del trabajo.
        received_at=datetime.fromtimestamp(int(timestamp), UTC),
        has_delivery_id=bool(delivery_id),
    )


@router.post("/chatwoot", response_model=WebhookAck)
async def receive_chatwoot_event(
    event: Annotated[VerifiedChatwootEvent, Depends(verified_chatwoot_event)],
    use_case: Annotated[
        ReceiveGatewayEvent, Depends(containers.get_receive_gateway_event_use_case)
    ],
) -> WebhookAck:
    log = get_logger("chatwoot_webhook")
    try:
        queued = await use_case.execute(
            event_id=event.event_id, raw_body=event.raw_body, received_at=event.received_at
        )
    except GatewayEventNotQueuedError as exc:
        log.error("gateway_event_not_queued", event_id=event.loggable_id, error_type=exc.error_type)
        raise ProblemError(
            503,
            "event-queue-unavailable",
            "Servicio no disponible",
            "No se pudo encolar el evento; puede reenviarse.",
        ) from exc
    if not queued:
        log.info("chatwoot_webhook_duplicate", event_id=event.loggable_id)
    return WebhookAck()
