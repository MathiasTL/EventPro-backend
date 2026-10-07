"""Coordina una extensión cobrada con evidencia y persistencia indivisible."""

import logging
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
from app.application.services.event_extension_availability import check_extension_availability
from app.application.use_cases.event.event_operation_access import authorize_event
from app.domain.entities.event_extension import validate_extension_terms
from app.domain.entities.payment import (
    Payment,
    PaymentAuditStatus,
    PaymentConcept,
    PaymentValidationStatus,
)
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError
from app.domain.exceptions.storage_exceptions import EvidenceValidationError

logger = logging.getLogger(__name__)


class RegisterEventExtensionUseCase:
    def __init__(
        self,
        events: IEventRepositoryPort,
        storage: IPaymentEvidenceStoragePort,
        crews: ICrewScheduleReadPort,
        clock: IClockPort,
        *,
        simultaneous_threshold: int = 3,
    ) -> None:
        self._events, self._storage, self._crews, self._clock = events, storage, crews, clock
        self._threshold = simultaneous_threshold

    async def execute(
        self, dto: RegisterEventExtensionInput, actor: ScheduleActor
    ) -> EventExtensionDTO:
        await authorize_event(dto.event_id, actor, self._crews)
        amount = validate_extension_terms(
            dto.extra_minutes, dto.agreed_rate, dto.payment_method, dto.transaction_reference
        )
        reference = dto.transaction_reference
        if not dto.evidence_data or len(dto.evidence_data) > self._storage.max_bytes():
            raise EvidenceValidationError("La evidencia es obligatoria y no puede superar 5 MiB.")
        now = self._clock.utcnow()
        payment_id = uuid4()
        path = await self._storage.store(
            data=dto.evidence_data,
            content_type=dto.evidence_content_type,
            original_filename=dto.evidence_filename,
        )
        persist_attempted = False
        try:
            await self._events.lock_availability()
            event = await self._events.get_by_id_for_update(dto.event_id)
            if event is None:
                raise ResourceNotFoundError("El evento no existe.")
            extension = event.extend(
                extra_minutes=dto.extra_minutes,
                agreed_rate=amount,
                payment_id=payment_id,
                requested_at=now,
            )
            occupancy = await self._events.load_occupancy(event, dto.extra_minutes)
            check_extension_availability(event, occupancy, self._threshold)
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
            persist_attempted = True
            await self._events.save_extension(event, extension, payment)
        except BaseException:
            rolled_back = False
            try:
                await self._events.rollback_operation()
                rolled_back = True
            except Exception:
                logger.exception("No se pudo confirmar el rollback de la extensión.")
            try:
                if not persist_attempted or (
                    rolled_back and await self._events.can_discard_extension_evidence(payment_id)
                ):
                    await self._storage.delete(path)
                else:
                    logger.warning(
                        "Se conserva la evidencia: el pago está persistido o su commit es incierto."
                    )
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
