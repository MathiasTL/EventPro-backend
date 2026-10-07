from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.entities.refresh_token import RefreshToken
from app.infrastructure.adapters.secondary.persistence.models.refresh_token import (
    RefreshToken as RefreshTokenModel,
)


class SQLAlchemyRefreshTokenRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add(self, token: RefreshToken) -> None:
        record = RefreshTokenModel(
            id=token.id,
            user_id=token.user_id,
            token_hash=token.token_hash,
            expires_at=token.expires_at,
            is_revoked=token.is_revoked,
            created_at=token.created_at,
        )
        async with self._session_factory() as session:
            session.add(record)
            await session.commit()

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        stmt = select(RefreshTokenModel).where(RefreshTokenModel.token_hash == token_hash)
        async with self._session_factory() as session:
            record = (await session.execute(stmt)).scalar_one_or_none()
        if record is None:
            return None
        return RefreshToken(
            id=record.id,
            user_id=record.user_id,
            token_hash=record.token_hash,
            expires_at=record.expires_at,
            is_revoked=record.is_revoked,
            created_at=record.created_at,
        )

    async def revoke(self, token_hash: str) -> None:
        async with self._session_factory() as session:
            await session.execute(
                update(RefreshTokenModel)
                .where(RefreshTokenModel.token_hash == token_hash)
                .values(is_revoked=True)
            )
            await session.commit()

    async def revoke_all_for_user(self, user_id: UUID) -> None:
        async with self._session_factory() as session:
            await session.execute(
                update(RefreshTokenModel)
                .where(
                    RefreshTokenModel.user_id == user_id,
                    RefreshTokenModel.is_revoked.is_(False),
                )
                .values(is_revoked=True)
            )
            await session.commit()
