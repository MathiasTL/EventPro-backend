"""Coordina una extensión cobrada con evidencia y persistencia indivisible."""

import logging
from decimal import Decimal
from uuid import uuid4

from app.application.dtos.event_extension_dto import (
    EventExtensionDTO,
    ExtensionPaymentDTO,
    RegisterEventExtensionInput,
)
from app.application.dtos.event_schedule_dto import ScheduleActor
from app.application.ports.output.clock_port import IClockPort
from app.application.ports.output.crew_schedule_read_port import ICrewScheduleReadPort
from app.application.ports.output.event_repository_port import IEventRepositoryPort
from app.application.ports.output.payment_evidence_storage_port import IPaymentEvidenceStoragePort
from app.application.use_cases.event.event_operation_access import authorize_event
from app.domain.entities.event_extension import MAX_AMOUNT
from app.domain.entities.payment import (
    Payment,
    PaymentAuditStatus,
    PaymentConcept,
    PaymentMethod,
    PaymentValidationStatus,
)
from app.domain.exceptions.event_exceptions import InvalidEvidenceError
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError, ValidationError
from app.domain.value_objects.money import Money

logger = logging.getLogger(__name__)


class RegisterEventExtensionUseCase:
    def __init__(
        self,
        events: IEventRepositoryPort,
        storage: IPaymentEvidenceStoragePort,
        crews: ICrewScheduleReadPort,
        clock: IClockPort,
    ) -> None:
        self._events, self._storage, self._crews, self._clock = events, storage, crews, clock

    async def execute(
        self, dto: RegisterEventExtensionInput, actor: ScheduleActor
    ) -> EventExtensionDTO:
        await authorize_event(dto.event_id, actor, self._crews)
        event = await self._events.get_by_id_for_update(dto.event_id)
        if event is None:
            raise ResourceNotFoundError("El evento no existe.")
        event.validate_operating_state()
        if (
            not isinstance(dto.agreed_rate, Decimal)
            or not dto.agreed_rate.is_finite()
            or not 0 < dto.agreed_rate <= MAX_AMOUNT
            or dto.agreed_rate != dto.agreed_rate.quantize(Decimal("0.01"))
        ):
            raise ValidationError("El importe debe ser un decimal finito con hasta dos decimales.")
        if not isinstance(dto.payment_method, PaymentMethod):
            raise ValidationError("El medio de pago no es válido.")
        reference = dto.transaction_reference
        if reference is not None and (not reference.strip() or len(reference) > 60):
            raise ValidationError("La referencia debe contener entre 1 y 60 caracteres.")
        if not dto.evidence_data or len(dto.evidence_data) > self._storage.max_bytes():
            raise InvalidEvidenceError("La evidencia es obligatoria y no puede superar 5 MiB.")
        now = self._clock.utcnow()
        payment_id = uuid4()
        extension = event.extend(
            extra_minutes=dto.extra_minutes,
            agreed_rate=Money(dto.agreed_rate),
            payment_id=payment_id,
            requested_at=now,
        )
        path = await self._storage.store(
            data=dto.evidence_data,
            content_type=dto.evidence_content_type,
            original_filename=dto.evidence_filename,
        )
        try:
            payment = Payment(
                id=payment_id,
                quote_id=event.quote_id,
                event_id=event.id,
                concept=PaymentConcept.EXTENSION,
                payment_method=dto.payment_method,
                amount=extension.agreed_rate,
                evidence_path=path,
                transaction_reference=reference,
                validation_status=PaymentValidationStatus.VERIFIED,
                audit_status=PaymentAuditStatus.UNREVIEWED,
                registered_by_user_id=actor.user_id,
                created_at=extension.requested_at,
            )
            await self._events.save_extension(event, extension, payment)
        except BaseException:
            try:
                if await self._events.can_discard_extension_evidence(payment_id):
                    await self._storage.delete(path)
            except Exception:
                logger.exception("No se pudo eliminar la evidencia de una extensión fallida.")
            raise
        return EventExtensionDTO(
            event.id,
            event.status,
            extension.id,
            ExtensionPaymentDTO(
                payment.id,
                PaymentConcept.EXTENSION,
                payment.amount.amount,
                PaymentValidationStatus.VERIFIED,
                PaymentAuditStatus.UNREVIEWED,
            ),
        )
