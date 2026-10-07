from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.elements import ColumnElement

from app.application.dtos.user_dto import UserFilters
from app.domain.entities.user import User
from app.domain.exceptions.resource_exceptions import (
    DuplicateResourceError,
    ResourceNotFoundError,
    ValidationError,
)
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.secondary.persistence.models.role import Role as RoleModel
from app.infrastructure.adapters.secondary.persistence.models.user import User as UserModel

_DUPLICATE_MESSAGE = "El correo o el teléfono ya están registrados."


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


def _filter_clauses(filters: UserFilters) -> list[ColumnElement[bool]]:
    clauses: list[ColumnElement[bool]] = []
    if filters.role is not None:
        clauses.append(RoleModel.code == filters.role.value)
    if filters.is_active is not None:
        clauses.append(UserModel.is_active.is_(filters.is_active))
    if filters.q and filters.q.strip():
        term = f"%{filters.q.strip().lower()}%"
        clauses.append(
            or_(
                func.lower(UserModel.full_name).like(term),
                func.lower(UserModel.email).like(term),
                func.lower(UserModel.phone).like(term),
            )
        )
    return clauses


async def _role_id(session: AsyncSession, role: Role) -> UUID:
    stmt = select(RoleModel.id).where(RoleModel.code == role.value)
    role_id = (await session.execute(stmt)).scalar_one_or_none()
    if role_id is None:
        raise ValidationError(f"El rol {role.value} no existe; ejecute el seed de roles.")
    return role_id


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

    async def add(self, user: User) -> None:
        async with self._session_factory() as session:
            record = UserModel(
                id=user.id,
                role_id=await _role_id(session, user.role),
                full_name=user.full_name,
                email=user.email,
                phone=user.phone,
                hashed_password=user.hashed_password,
                is_active=user.is_active,
                created_at=user.created_at,
            )
            session.add(record)
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise DuplicateResourceError(_DUPLICATE_MESSAGE) from exc

    async def update(self, user: User) -> None:
        async with self._session_factory() as session:
            record = await session.get(UserModel, user.id)
            if record is None:
                raise ResourceNotFoundError("El usuario no existe.")
            record.role_id = await _role_id(session, user.role)
            record.full_name = user.full_name
            record.phone = user.phone
            record.hashed_password = user.hashed_password
            record.is_active = user.is_active
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise DuplicateResourceError(_DUPLICATE_MESSAGE) from exc

    async def list(self, filters: UserFilters) -> Sequence[User]:
        stmt = (
            select(UserModel, RoleModel.code)
            .join(RoleModel, UserModel.role_id == RoleModel.id)
            .where(*_filter_clauses(filters))
            .order_by(func.lower(UserModel.full_name), UserModel.email)
            .offset((max(1, filters.page) - 1) * max(1, filters.page_size))
            .limit(max(1, filters.page_size))
        )
        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).all()
        return [_to_domain(user_model, role_code) for user_model, role_code in rows]

    async def count(self, filters: UserFilters) -> int:
        inner = (
            select(UserModel.id)
            .join(RoleModel, UserModel.role_id == RoleModel.id)
            .where(*_filter_clauses(filters))
        )
        stmt = select(func.count()).select_from(inner.subquery())
        async with self._session_factory() as session:
            return int((await session.execute(stmt)).scalar_one())
