"""Database-backed quote and crew details for the event schedule."""

from collections import defaultdict
from collections.abc import Mapping
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.event_schedule_dto import CrewScheduleDTO, QuoteScheduleDTO
from app.core.logging import get_logger
from app.infrastructure.adapters.secondary.persistence.models.catalog_models import (
    CrewModel,
    PackageModel,
    ThemeModel,
)
from app.infrastructure.adapters.secondary.persistence.models.client_model import ClientModel
from app.infrastructure.adapters.secondary.persistence.models.event_resource_models import (
    CrewAssignmentModel,
)
from app.infrastructure.adapters.secondary.persistence.models.quote_model import QuoteModel

logger = get_logger(__name__)

_MISSING_QUOTE = QuoteScheduleDTO(
    client_name="Cliente no disponible",
    package_name="Paquete no disponible",
    theme_name="Sin temática",
)


class SqlAlchemyQuoteScheduleReadAdapter:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_details(self, quote_ids: frozenset[UUID]) -> Mapping[UUID, QuoteScheduleDTO]:
        if not quote_ids:
            return {}
        rows = (
            await self._session.execute(
                select(
                    QuoteModel.id,
                    ClientModel.full_name,
                    PackageModel.name,
                    ThemeModel.name,
                )
                .select_from(QuoteModel)
                .join(ClientModel, ClientModel.id == QuoteModel.client_id)
                .join(PackageModel, PackageModel.id == QuoteModel.package_id)
                .outerjoin(ThemeModel, ThemeModel.id == QuoteModel.theme_id)
                .where(QuoteModel.id.in_(quote_ids))
            )
        ).all()
        details = {
            quote_id: QuoteScheduleDTO(client_name, package_name, theme_name or "Sin temática")
            for quote_id, client_name, package_name, theme_name in rows
        }
        missing = quote_ids - details.keys()
        if missing:
            logger.warning("schedule_quote_details_missing", quote_ids=sorted(map(str, missing)))
            details.update({quote_id: _MISSING_QUOTE for quote_id in missing})
        return details


class SqlAlchemyCrewScheduleReadAdapter:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_assigned_event_ids(self, user_id: UUID) -> frozenset[UUID]:
        rows = (
            await self._session.execute(
                select(CrewAssignmentModel.event_id)
                .select_from(CrewAssignmentModel)
                .join(CrewModel, CrewModel.id == CrewAssignmentModel.crew_id)
                .where(CrewModel.user_id == user_id, CrewModel.is_active.is_(True))
            )
        ).scalars()
        return frozenset(rows)

    async def get_crews(
        self, event_ids: frozenset[UUID]
    ) -> Mapping[UUID, tuple[CrewScheduleDTO, ...]]:
        if not event_ids:
            return {}
        rows = (
            await self._session.execute(
                select(
                    CrewAssignmentModel.event_id,
                    CrewModel.id,
                    CrewModel.leader_name,
                )
                .select_from(CrewAssignmentModel)
                .join(CrewModel, CrewModel.id == CrewAssignmentModel.crew_id)
                .where(CrewAssignmentModel.event_id.in_(event_ids))
                .order_by(CrewModel.leader_name, CrewModel.id)
            )
        ).all()
        crews: dict[UUID, list[CrewScheduleDTO]] = defaultdict(list)
        for event_id, crew_id, leader_name in rows:
            crews[event_id].append(CrewScheduleDTO(crew_id, leader_name))
        return {event_id: tuple(crews[event_id]) for event_id in event_ids}
