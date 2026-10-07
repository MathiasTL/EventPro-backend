from app.application.dtos.event_occupancy_dto import EventOccupancy
from app.domain.entities.event import Event
from app.domain.exceptions.event_exceptions import EventResourceConflictError
from app.domain.services.concurrency_evaluator import ConcurrencyEvaluator
from app.domain.services.inventory_availability import InventoryAvailabilityService
from app.domain.services.travel_interval_service import TravelIntervalService


def check_extension_availability(event: Event, occupancy: EventOccupancy, threshold: int) -> None:
    window = event.time_window
    if ConcurrencyEvaluator(threshold).requires_manual_approval(
        occupancy.simultaneous_windows, window
    ):
        raise EventResourceConflictError("La extensión requiere aprobación manual por sobrecupo.")
    inventory = InventoryAvailabilityService()
    for item in occupancy.inventory:
        if not inventory.check(item.total_stock, item.reservations, item.request).is_available:
            raise EventResourceConflictError("El inventario no cubre el horario extendido.")
    crew_ids = {assignment.crew_id for assignment in occupancy.crews}
    travel = TravelIntervalService()
    for crew_id in crew_ids:
        assignments = [row for row in occupancy.crews if row.crew_id == crew_id]
        if any(row.window.overlaps(window) for row in assignments):
            raise EventResourceConflictError("El elenco tiene otro evento en el horario extendido.")
        following = [row for row in assignments if row.window.start >= window.end]
        if following:
            next_event = min(following, key=lambda row: row.window.start)
            if next_event.transit_interval_minutes is None:
                raise EventResourceConflictError(
                    "Falta el intervalo de traslado del siguiente evento."
                )
            if not travel.is_feasible(
                window,
                next_event.window,
                transit_minutes=0,
                override_minutes=next_event.transit_interval_minutes,
            ):
                raise EventResourceConflictError(
                    "El tiempo disponible no permite el traslado del elenco."
                )
