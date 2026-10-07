"""Alcance de las operaciones US-18, según la matriz RBAC."""

from uuid import UUID

from app.application.dtos.event_schedule_dto import ScheduleActor
from app.application.ports.output.crew_schedule_read_port import ICrewScheduleReadPort
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError
from app.domain.value_objects.role import Role


async def authorize_event(
    event_id: UUID, actor: ScheduleActor, crews: ICrewScheduleReadPort
) -> None:
    if actor.role not in (Role.ENCARGADO, Role.SUPERADMIN, Role.OPERADOR):
        raise PermissionError("El rol no tiene permiso para operar eventos.")
    if actor.role is Role.OPERADOR and event_id not in await crews.get_assigned_event_ids(
        actor.user_id
    ):
        raise ResourceNotFoundError("El evento no existe.")
