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
from app.application.ports.output.contract_port import IContractIssuer
from app.application.ports.output.event_repository_port import IEventRepositoryPort
from app.application.ports.output.payment_repository_port import IPaymentRepositoryPort
from app.application.ports.output.quote_event_port import IQuoteEventProvisioner
from app.application.services.audit_service import AuditService
from app.domain.entities.payment import PaymentValidationStatus
from app.domain.exceptions.payment_exceptions import InvalidPaymentStateError
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError, ValidationError


class ApproveOverbookedPaymentUseCase:
    """Aprueba o rechaza el sobrecupo de un adelanto."""

    def __init__(
        self,
        payments: IPaymentRepositoryPort,
        audit: AuditService,
        events: IEventRepositoryPort,
        contracts: IContractIssuer | None = None,
        quote_events: IQuoteEventProvisioner | None = None,
    ) -> None:
        self._payments = payments
        self._audit = audit
        self._events = events
        self._contracts = contracts
        self._quote_events = quote_events

    async def execute(self, dto: ApproveOverbookedInput) -> ApproveOverbookedDTO:
        payment = await self._payments.get_by_id(dto.payment_id)
        if payment is None:
            raise ResourceNotFoundError("Pago no encontrado")

        previous_status = payment.validation_status.value
        now = datetime.now(UTC)

        if dto.decision is OverbookedDecision.APPROVE:
            event_id = dto.event_id
            if event_id is None:
                if self._quote_events is None or self._contracts is None:
                    raise ValidationError("event_id es obligatorio para aprobar el sobrecupo")
                if (
                    payment.validation_status
                    is not PaymentValidationStatus.REQUIRES_MANUAL_APPROVAL
                ):
                    raise InvalidPaymentStateError("El pago no requiere aprobación manual.")
                # La aprobación es el sobrecupo autorizado: no se revalida el cupo.
                event_id = await self._quote_events.ensure_event(
                    payment.quote_id, check_availability=False
                )
                assert event_id is not None
            elif await self._events.get_by_id_for_update(event_id) is None:
                raise ResourceNotFoundError("Evento no encontrado")
            if self._contracts is not None:
                await self._contracts.prepare_payment_event(event_id, payment.quote_id)
            payment.approve_overbooked(
                verified_by_user_id=dto.decided_by_user_id,
                event_id=event_id,
                approved_at=now,
            )
            action = "APPROVE_OVERBOOKED_PAYMENT"
        else:
            payment.mark_refund_pending()
            action = "REJECT_OVERBOOKED_PAYMENT"

        await self._payments.save(payment)
        if (
            dto.decision is OverbookedDecision.APPROVE
            and self._contracts is not None
            and payment.event_id is not None
        ):
            await self._contracts.issue_for_event(payment.event_id, dto.decided_by_user_id)
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
            event_created_id=payment.event_id
            if dto.decision is OverbookedDecision.APPROVE
            else None,
        )
