"""Adaptador de disponibilidad: implementa ``IAvailabilityPort`` (E3).

Compone los servicios de dominio (inventario, concurrencia y tránsito) con las
consultas de persistencia y el lock distribuido (ADR-06). Es el contrato que usan el
cotizador (E1) antes de confirmar una cotización, el pago (E5) en la revalidación
autoritativa y la asignación de elencos (E6).

Precedencia del resultado: si el inventario no alcanza, el resultado es ``CONFLICT``;
si el inventario alcanza pero se supera el umbral de simultaneidad, es
``REQUIRES_MANUAL_APPROVAL``; en caso contrario, ``AVAILABLE``. El resultado siempre
incluye ``simultaneous_count`` y los faltantes, para que cada consumidor aplique su
propia política (por ejemplo, US-11 manda que en la recepción del comprobante tanto
el cupo lleno como el umbral superado lleven el pago a ``REQUIRES_MANUAL_APPROVAL``).
"""

from __future__ import annotations

from app.application.dtos.availability_dto import (
    AvailabilityRequest,
    AvailabilityResult,
    AvailabilityStatus,
    CrewTransitRequest,
    CrewTransitResult,
    InventoryShortageDTO,
)
from app.application.ports.output.availability_port import IAvailabilityPort
from app.application.ports.output.cache_lock_port import ICacheLockPort
from app.domain.services.concurrency_evaluator import ConcurrencyEvaluator
from app.domain.services.inventory_availability import (
    InventoryAvailabilityService,
    InventoryRequest,
    InventoryReservation,
)
from app.domain.services.travel_interval_service import TravelIntervalService
from app.domain.value_objects.time_window import TimeWindow
from app.infrastructure.adapters.secondary.persistence import (
    SqlAlchemyAvailabilityRepository,
)
from app.infrastructure.adapters.secondary.persistence.models.availability_models import (
    InventoryReservationModel,
)

_LOCK_TTL_SECONDS = 30
_LOCK_WAIT_SECONDS = 2.0


class AvailabilityAdapter(IAvailabilityPort):
    """Motor de disponibilidad sobre PostgreSQL y Redis."""

    def __init__(
        self,
        repository: SqlAlchemyAvailabilityRepository,
        lock: ICacheLockPort,
        concurrency_evaluator: ConcurrencyEvaluator,
        inventory_availability: InventoryAvailabilityService,
        travel_interval_service: TravelIntervalService,
    ) -> None:
        self._repository = repository
        self._lock = lock
        self._concurrency = concurrency_evaluator
        self._inventory = inventory_availability
        self._travel = travel_interval_service

    async def check_availability(self, request: AvailabilityRequest) -> AvailabilityResult:
        window = TimeWindow.from_schedule(
            request.event_date, request.start_time, request.duration_minutes
        )

        lock_key = (
            f"availability:{request.package_id}:"
            f"{request.event_date.isoformat()}T{request.start_time.isoformat()}"
        )
        acquired = await self._lock.acquire(
            lock_key, ttl_seconds=_LOCK_TTL_SECONDS, wait_seconds=_LOCK_WAIT_SECONDS
        )
        try:
            requirements = await self._repository.get_package_inventory_requirements(
                request.package_id
            )
            reservations = await self._repository.list_active_reservations(
                [requirement.inventory_item_id for requirement in requirements], window
            )

            shortages: list[InventoryShortageDTO] = []
            for requirement in requirements:
                item_reservations = tuple(
                    _to_domain(reservation)
                    for reservation in reservations
                    if reservation.inventory_item_id == requirement.inventory_item_id
                )
                check = self._inventory.check(
                    requirement.total_stock,
                    item_reservations,
                    InventoryRequest(requirement.inventory_item_id, requirement.quantity, window),
                )
                if not check.is_available:
                    shortages.append(
                        InventoryShortageDTO(
                            inventory_item_id=requirement.inventory_item_id,
                            requested=check.requested_quantity,
                            available=check.available_quantity,
                        )
                    )

            countable_events = await self._repository.list_countable_events(window)
            simultaneous_count = self._concurrency.simultaneous_count(
                [row.window for row in countable_events], window
            )

            status = AvailabilityStatus.AVAILABLE
            if shortages:
                status = AvailabilityStatus.CONFLICT
            elif simultaneous_count > self._concurrency.threshold:
                status = AvailabilityStatus.REQUIRES_MANUAL_APPROVAL

            return AvailabilityResult(
                status=status,
                simultaneous_count=simultaneous_count,
                shortages=tuple(shortages),
            )
        finally:
            # La verificación es informativa: si el lock está tomado por otra operación
            # se igual revisa; quien escriba la reserva debe hacerlo en su propia
            # sección crítica para cerrar la puerta a la doble reserva.
            if acquired:
                await self._lock.release(lock_key)

    async def check_crew_transit(self, request: CrewTransitRequest) -> CrewTransitResult:
        gap_minutes = int((request.candidate_start - request.previous_end).total_seconds() // 60)
        required_minutes = self._travel.required_interval_minutes(
            request.transit_minutes, request.override_minutes
        )
        feasible = self._travel.is_gap_feasible(
            gap_minutes, request.transit_minutes, request.override_minutes
        )
        return CrewTransitResult(
            feasible=feasible,
            required_minutes=required_minutes,
            available_gap_minutes=gap_minutes,
        )


def _to_domain(reservation: InventoryReservationModel) -> InventoryReservation:
    """Convierte una reserva ORM en el objeto de dominio que evalúa el servicio."""

    return InventoryReservation(
        inventory_item_id=reservation.inventory_item_id,
        quantity=reservation.quantity,
        window=TimeWindow(reservation.starts_at, reservation.ends_at),
    )
