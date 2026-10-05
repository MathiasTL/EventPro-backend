import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

HEALTH_TIMEOUT_SECONDS = 2.0


class SQLAlchemyHealthAdapter:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def ping(self) -> bool:
        try:
            async with asyncio.timeout(HEALTH_TIMEOUT_SECONDS):
                async with self._engine.connect() as connection:
                    await connection.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
