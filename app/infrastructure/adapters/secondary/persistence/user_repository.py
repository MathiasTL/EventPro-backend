from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.entities.user import User
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.secondary.persistence.models.role import Role as RoleModel
from app.infrastructure.adapters.secondary.persistence.models.user import User as UserModel


def _to_domain(user_model: UserModel, role_code: str) -> User:
    return User(
        id=user_model.id,
        full_name=user_model.full_name,
        email=user_model.email,
        phone=user_model.phone,
        role=Role(role_code),
        hashed_password=user_model.hashed_password,
        is_active=user_model.is_active,
        created_at=user_model.created_at,
    )


class SQLAlchemyUserRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_by_email(self, email: str) -> User | None:
        stmt = (
            select(UserModel, RoleModel.code)
            .join(RoleModel, UserModel.role_id == RoleModel.id)
            .where(func.lower(UserModel.email) == email.strip().lower())
        )
        async with self._session_factory() as session:
            row = (await session.execute(stmt)).first()
        if row is None:
            return None
        user_model, role_code = row
        return _to_domain(user_model, role_code)

    async def get_by_id(self, user_id: UUID) -> User | None:
        stmt = (
            select(UserModel, RoleModel.code)
            .join(RoleModel, UserModel.role_id == RoleModel.id)
            .where(UserModel.id == user_id)
        )
        async with self._session_factory() as session:
            row = (await session.execute(stmt)).first()
        if row is None:
            return None
        user_model, role_code = row
        return _to_domain(user_model, role_code)
