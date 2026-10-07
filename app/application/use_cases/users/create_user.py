"""Alta de usuarios del panel (solo SUPERADMIN)."""

from uuid import uuid4

from app.application.dtos.user_dto import CreateUserInput, UserReadDTO
from app.application.ports.output.user_repository_port import IUserRepositoryPort
from app.application.use_cases.users.mappers import to_user_dto
from app.core.security import hash_password
from app.domain.entities.user import User
from app.domain.exceptions.resource_exceptions import DuplicateResourceError


class CreateUserUseCase:
    def __init__(self, users: IUserRepositoryPort) -> None:
        self._users = users

    async def execute(self, data: CreateUserInput) -> UserReadDTO:
        email = data.email.strip()
        phone = data.phone.strip()
        if await self._users.get_by_email(email) is not None:
            raise DuplicateResourceError("El correo ya está registrado.")
        user = User(
            id=uuid4(),
            full_name=data.full_name.strip(),
            email=email,
            phone=phone,
            role=data.role,
            hashed_password=hash_password(data.password),
            is_active=True,
        )
        await self._users.add(user)
        return to_user_dto(user)
