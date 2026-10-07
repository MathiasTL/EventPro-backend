"""Actualización de datos, rol, estado o contraseña de un usuario (US-23)."""

from uuid import UUID

from app.application.dtos.user_dto import UpdateUserInput, UserReadDTO
from app.application.ports.output.refresh_token_repository_port import IRefreshTokenRepositoryPort
from app.application.ports.output.user_repository_port import IUserRepositoryPort
from app.application.use_cases.users.errors import SelfModificationError
from app.application.use_cases.users.mappers import to_user_dto
from app.core.security import hash_password
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError
from app.domain.value_objects.role import Role


class UpdateUserUseCase:
    def __init__(
        self,
        users: IUserRepositoryPort,
        tokens: IRefreshTokenRepositoryPort,
    ) -> None:
        self._users = users
        self._tokens = tokens

    async def execute(self, actor_id: UUID, user_id: UUID, data: UpdateUserInput) -> UserReadDTO:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise ResourceNotFoundError("El usuario no existe.")
        if user_id == actor_id:
            if data.is_active is False:
                raise SelfModificationError("No puedes desactivar tu propia cuenta.")
            if data.role is not None and data.role is not Role.SUPERADMIN:
                raise SelfModificationError("No puedes cambiar tu propio rol de SUPERADMIN.")
        if data.full_name is not None:
            user.full_name = data.full_name.strip()
        if data.phone is not None:
            user.phone = data.phone.strip()
        if data.role is not None:
            user.role = data.role
        if data.is_active is not None:
            user.is_active = data.is_active
        if data.password is not None:
            user.hashed_password = hash_password(data.password)
        await self._users.update(user)
        if data.is_active is False or data.password is not None:
            await self._tokens.revoke_all_for_user(user_id)
        return to_user_dto(user)
