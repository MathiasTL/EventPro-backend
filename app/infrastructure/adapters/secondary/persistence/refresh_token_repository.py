from datetime import datetime
from typing import Any

from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.entities.refresh_token import RefreshToken
from app.infrastructure.adapters.secondary.persistence.models.refresh_token import (
    RefreshToken as RefreshTokenModel,
)
from app.infrastructure.adapters.secondary.persistence.models.user import User as UserModel


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

    async def revoke(self, token_hash: str) -> bool:
        async with self._session_factory() as session:
            result: CursorResult[Any] = await session.execute(  # type: ignore[assignment]
                update(RefreshTokenModel)
                .where(
                    RefreshTokenModel.token_hash == token_hash,
                    RefreshTokenModel.is_revoked.is_(False),
                )
                .values(is_revoked=True)
            )
            await session.commit()
        return bool(result.rowcount)

    async def rotate(self, old_token_hash: str, new_token: RefreshToken, now: datetime) -> bool:
        async with self._session_factory() as session:
            try:
                # Misma fila que bloquea UserRepository.update: si hay un PATCH en
                # curso, esperamos a que confirme y vemos sus revocaciones.
                is_active = await session.scalar(
                    select(UserModel.is_active)
                    .where(UserModel.id == new_token.user_id)
                    .with_for_update()
                )
                if not is_active:
                    await session.rollback()
                    return False
                result: CursorResult[Any] = await session.execute(  # type: ignore[assignment]
                    update(RefreshTokenModel)
                    .where(
                        RefreshTokenModel.token_hash == old_token_hash,
                        RefreshTokenModel.user_id == new_token.user_id,
                        RefreshTokenModel.is_revoked.is_(False),
                        RefreshTokenModel.expires_at > now,
                    )
                    .values(is_revoked=True)
                )
                if not result.rowcount:
                    await session.rollback()
                    return False
                session.add(
                    RefreshTokenModel(
                        id=new_token.id,
                        user_id=new_token.user_id,
                        token_hash=new_token.token_hash,
                        expires_at=new_token.expires_at,
                        is_revoked=new_token.is_revoked,
                        created_at=new_token.created_at,
                    )
                )
                await session.commit()
            except Exception:
                await session.rollback()
                raise
        return True
