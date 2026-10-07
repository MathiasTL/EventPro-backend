"""RF-20 / US-10: resolución manual de un pago en ``REQUIRES_MANUAL_APPROVAL``.

El encargado aprueba el sobrecupo (el pago pasa a ``VERIFIED``) o lo rechaza (el pago
pasa a ``REFUND_PENDING`` y luego a ``REFUNDED``). La aprobación es un **estado del
pago**, no del evento (RN-04). Cada decisión se registra en la bitácora.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.application.dtos.override_dto import (
    ApproveOverbookedDTO,
    ApproveOverbookedInput,
    OverbookedDecision,
)
from app.application.ports.output.event_repository_port import IEventRepositoryPort
from app.application.ports.output.payment_repository_port import IPaymentRepositoryPort
from app.application.services.audit_service import AuditService
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError, ValidationError


class ApproveOverbookedPaymentUseCase:
    """Aprueba o rechaza el sobrecupo de un adelanto."""

    def __init__(
        self, payments: IPaymentRepositoryPort, audit: AuditService, events: IEventRepositoryPort
    ) -> None:
        self._payments = payments
        self._audit = audit
        self._events = events

    async def execute(self, dto: ApproveOverbookedInput) -> ApproveOverbookedDTO:
        payment = await self._payments.get_by_id(dto.payment_id)
        if payment is None:
            raise ResourceNotFoundError("Pago no encontrado")

        previous_status = payment.validation_status.value
        now = datetime.now(UTC)

        if dto.decision is OverbookedDecision.APPROVE:
            if dto.event_id is None:
                raise ValidationError("event_id es obligatorio para aprobar el sobrecupo")
            if await self._events.get_by_id_for_update(dto.event_id) is None:
                raise ResourceNotFoundError("Evento no encontrado")
            payment.approve_overbooked(
                verified_by_user_id=dto.decided_by_user_id,
                event_id=dto.event_id,
                approved_at=now,
            )
            action = "APPROVE_OVERBOOKED_PAYMENT"
        else:
            payment.mark_refund_pending()
            action = "REJECT_OVERBOOKED_PAYMENT"

        await self._payments.save(payment)
        await self._audit.record(
            action=action,
            entity_name="payments",
            entity_id=payment.id,
            user_id=dto.decided_by_user_id,
            old_values={"validation_status": previous_status},
            new_values={
                "validation_status": payment.validation_status.value,
                "notes": dto.notes,
            },
        )

        return ApproveOverbookedDTO(
            payment_id=payment.id,
            validation_status=payment.validation_status,
            event_created_id=dto.event_id if dto.decision is OverbookedDecision.APPROVE else None,
        )
