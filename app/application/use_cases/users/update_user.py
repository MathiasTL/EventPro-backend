"""Actualización de datos, rol, estado o contraseña de un usuario (US-23)."""

from uuid import UUID

from app.application.dtos.user_dto import UpdateUserInput, UserPatch, UserReadDTO
from app.application.ports.output.user_repository_port import IUserRepositoryPort
from app.application.use_cases.users.errors import SelfModificationError
from app.application.use_cases.users.mappers import to_user_dto
from app.core.security import hash_password
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError
from app.domain.value_objects.role import Role


class UpdateUserUseCase:
    def __init__(self, users: IUserRepositoryPort) -> None:
        self._users = users

    async def execute(self, actor_id: UUID, user_id: UUID, data: UpdateUserInput) -> UserReadDTO:
        """Aplica el parche de forma atómica en el repositorio.

        Solo se envían los campos indicados (nunca una copia leída antes), y la
        revocación de refresh tokens viaja en el mismo parche para que ocurra en
        la misma transacción que la actualización. El repositorio garantiza el
        invariante del último SUPERADMIN activo.
        """
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise ResourceNotFoundError("El usuario no existe.")
        if user_id == actor_id:
            if data.is_active is False:
                raise SelfModificationError("No puedes desactivar tu propia cuenta.")
            if data.role is not None and data.role is not Role.SUPERADMIN:
                raise SelfModificationError("No puedes cambiar tu propio rol de SUPERADMIN.")
        patch = UserPatch(
            full_name=data.full_name.strip() if data.full_name is not None else None,
            phone=data.phone.strip() if data.phone is not None else None,
            role=data.role,
            is_active=data.is_active,
            password_hash=hash_password(data.password) if data.password is not None else None,
            revoke_refresh_tokens=data.is_active is False or data.password is not None,
        )
        updated = await self._users.update(user_id, patch)
        return to_user_dto(updated)
