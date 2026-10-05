from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.entities.audit_log import AuditLog
from app.infrastructure.adapters.secondary.persistence.models.audit_log import (
    AuditLog as AuditLogModel,
)


class SQLAlchemyAuditLogAdapter:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def record(self, entry: AuditLog) -> None:
        async with self._session_factory() as session:
            session.add(
                AuditLogModel(
                    id=entry.id,
                    user_id=entry.user_id,
                    action=entry.action,
                    entity_name=entry.entity_name,
                    entity_id=entry.entity_id,
                    old_values=entry.old_values,
                    new_values=entry.new_values,
                )
            )
            await session.commit()
