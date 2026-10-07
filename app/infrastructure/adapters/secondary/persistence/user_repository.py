from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, or_, select, text
from sqlalchemy import update as sql_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.elements import ColumnElement

from app.application.dtos.user_dto import UserFilters, UserPatch
from app.domain.entities.user import User
from app.domain.exceptions.resource_exceptions import (
    DuplicateResourceError,
    ResourceNotFoundError,
    ValidationError,
)
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.secondary.persistence.models.refresh_token import (
    RefreshToken as RefreshTokenModel,
)
from app.infrastructure.adapters.secondary.persistence.models.role import Role as RoleModel
from app.infrastructure.adapters.secondary.persistence.models.user import User as UserModel

_DUPLICATE_MESSAGE = "El correo o el teléfono ya están registrados."
_LAST_SUPERADMIN_MESSAGE = "Debe permanecer al menos un SUPERADMIN activo."
# Clave estable del advisory lock ("USER" en ASCII): serializa las mutaciones de
# usuarios para conservar el invariante del último SUPERADMIN activo.
_USER_UPDATE_LOCK_KEY = 0x55534552


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


def _like_literal(value: str) -> str:
    """Envuelve el término en comodines LIKE escapando `%`, `_` y `\\`."""
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _filter_clauses(filters: UserFilters) -> list[ColumnElement[bool]]:
    clauses: list[ColumnElement[bool]] = []
    if filters.role is not None:
        clauses.append(RoleModel.code == filters.role.value)
    if filters.is_active is not None:
        clauses.append(UserModel.is_active.is_(filters.is_active))
    if filters.q and filters.q.strip():
        term = _like_literal(filters.q.strip().lower())
        clauses.append(
            or_(
                func.lower(UserModel.full_name).like(term, escape="\\"),
                func.lower(UserModel.email).like(term, escape="\\"),
                func.lower(UserModel.phone).like(term, escape="\\"),
            )
        )
    return clauses


async def _role_id(session: AsyncSession, role: Role) -> UUID:
    stmt = select(RoleModel.id).where(RoleModel.code == role.value)
    role_id = (await session.execute(stmt)).scalar_one_or_none()
    if role_id is None:
        raise ValidationError(f"El rol {role.value} no existe; ejecute el seed de roles.")
    return role_id


async def _lock_users(session: AsyncSession) -> None:
    """Advisory lock de transacción: serializa toda actualización de usuarios."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"), {"key": _USER_UPDATE_LOCK_KEY}
    )


async def _revoke_refresh_tokens(session: AsyncSession, user_id: UUID) -> None:
    """Revoca los refresh tokens vigentes del usuario dentro de la transacción dada."""
    await session.execute(
        sql_update(RefreshTokenModel)
        .where(
            RefreshTokenModel.user_id == user_id,
            RefreshTokenModel.is_revoked.is_(False),
        )
        .values(is_revoked=True)
    )


async def _active_superadmins_outside(session: AsyncSession, user_id: UUID) -> int:
    stmt = (
        select(func.count())
        .select_from(UserModel)
        .join(RoleModel, UserModel.role_id == RoleModel.id)
        .where(
            RoleModel.code == Role.SUPERADMIN.value,
            UserModel.is_active.is_(True),
            UserModel.id != user_id,
        )
    )
    return int((await session.execute(stmt)).scalar_one())


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

    async def update(self, user_id: UUID, patch: UserPatch) -> User:
        """Actualización parche atómica (ver :class:`IUserRepositoryPort`).

        Toma el advisory lock de usuarios y bloquea la fila del objetivo antes de
        leerla, de modo que el estado que se evalúa es el vigente:

        * solo se escriben los campos con valor del patch (un PATCH de nombre no
          puede revertir una desactivación ni pisar rol o contraseña concurrentes);
        * si la operación quita el estado de SUPERADMIN activo al objetivo y no
          queda ningún otro, se aborta con :class:`ValidationError` — la guarda es
          un backstop de concurrencia, ya que en secuencia el propio actor (por la
          autoprohibición de modificación a sí mismo) siempre sería ese otro;
        * la revocación de refresh tokens ocurre en la misma transacción, de modo
          que un fallo posterior deshace también el cambio de contraseña/estado.
        """
        async with self._session_factory() as session:
            try:
                await _lock_users(session)
                stmt = (
                    select(UserModel, RoleModel.code)
                    .join(RoleModel, UserModel.role_id == RoleModel.id)
                    .where(UserModel.id == user_id)
                    .with_for_update(of=UserModel)
                )
                row = (await session.execute(stmt)).first()
                if row is None:
                    raise ResourceNotFoundError("El usuario no existe.")
                record, previous_role_code = row
                was_active_superadmin = (
                    previous_role_code == Role.SUPERADMIN.value and record.is_active
                )

                if patch.role is not None:
                    record.role_id = await _role_id(session, patch.role)
                if patch.full_name is not None:
                    record.full_name = patch.full_name
                if patch.phone is not None:
                    record.phone = patch.phone
                if patch.password_hash is not None:
                    record.hashed_password = patch.password_hash
                if patch.is_active is not None:
                    record.is_active = patch.is_active

                still_active_superadmin = record.is_active and (
                    patch.role is Role.SUPERADMIN
                    if patch.role is not None
                    else previous_role_code == Role.SUPERADMIN.value
                )
                if (
                    was_active_superadmin
                    and not still_active_superadmin
                    and await _active_superadmins_outside(session, user_id) == 0
                ):
                    raise ValidationError(_LAST_SUPERADMIN_MESSAGE)

                if patch.revoke_refresh_tokens:
                    await _revoke_refresh_tokens(session, user_id)

                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise DuplicateResourceError(_DUPLICATE_MESSAGE) from exc
            except Exception:
                await session.rollback()
                raise
        updated = await self.get_by_id(user_id)
        if updated is None:
            raise ResourceNotFoundError("El usuario no existe.")
        return updated

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
