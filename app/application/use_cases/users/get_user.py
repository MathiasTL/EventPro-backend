"""Detalle de un usuario del panel."""

from uuid import UUID

from app.application.dtos.user_dto import UserReadDTO
from app.application.ports.output.user_repository_port import IUserRepositoryPort
from app.application.use_cases.users.mappers import to_user_dto
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError


class GetUserUseCase:
    def __init__(self, users: IUserRepositoryPort) -> None:
        self._users = users

    async def execute(self, user_id: UUID) -> UserReadDTO:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise ResourceNotFoundError("El usuario no existe.")
        return to_user_dto(user)
