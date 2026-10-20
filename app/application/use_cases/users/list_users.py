"""Listado paginado de usuarios del panel con filtros."""

from app.application.dtos.user_dto import UserFilters, UserPageDTO
from app.application.ports.output.user_repository_port import IUserRepositoryPort
from app.application.use_cases.users.mappers import to_user_dto


class ListUsersUseCase:
    def __init__(self, users: IUserRepositoryPort) -> None:
        self._users = users

    async def execute(self, filters: UserFilters) -> UserPageDTO:
        items = await self._users.list(filters)
        total = await self._users.count(filters)
        return UserPageDTO(
            items=[to_user_dto(item) for item in items],
            page=filters.page,
            page_size=filters.page_size,
            total=total,
        )
