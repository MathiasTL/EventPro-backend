"""US-22: una lectura PostgreSQL coherente, sin cargar eventos individuales."""

from collections.abc import Mapping
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import String, cast, func, literal_column, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select
from sqlalchemy.sql.elements import ColumnElement

from app.core.logging import get_logger
from app.domain.exceptions.financial_exceptions import FinancialDataInconsistentError
from app.domain.value_objects.dashboard import (
    DashboardReadData,
    DashboardWindow,
    DistrictTotals,
    ExtraRanking,
    MonthlyTotals,
    PackageMetric,
    ThemeMetric,
)
from app.domain.value_objects.financial_reporting import FinancialTotals
from app.domain.value_objects.money import Money
from app.infrastructure.adapters.secondary.persistence.models.catalog_models import (
    ExtraModel,
    PackageModel,
    ThemeModel,
)
from app.infrastructure.adapters.secondary.persistence.models.event_financial_snapshot_model import (  # noqa: E501
    EventFinancialSnapshotModel,
)
from app.infrastructure.adapters.secondary.persistence.models.event_model import EventModel
from app.infrastructure.adapters.secondary.persistence.models.quote_model import (
    QuoteExtraModel,
    QuoteModel,
)

logger = get_logger(__name__)
_AMOUNTS = (
    "gross_revenue",
    "fixed_packages_cost",
    "fixed_extras_cost",
    "mobility_operational_cost",
)


def _collection(statement: Select[Any]) -> ColumnElement[Any]:
    rows = statement.subquery()
    # NUMERIC se convierte a texto antes de JSONB: asyncpg no lo decodifica como float.
    fields = [item for column in rows.c for item in (column.key, column)]
    return (
        select(
            func.coalesce(
                func.jsonb_agg(func.jsonb_build_object(*fields)),
                literal_column("'[]'::jsonb", type_=JSONB),
            )
        )
        .select_from(rows)
        .scalar_subquery()
    )


def dashboard_statement(window: DashboardWindow) -> Select[Any]:
    snapshot = EventFinancialSnapshotModel
    base = (
        select(
            EventModel.id,
            EventModel.quote_id,
            EventModel.event_date,
            EventModel.district,
            snapshot.event_id.label("snapshot_id"),
            *(getattr(snapshot, name) for name in _AMOUNTS),
        )
        .select_from(EventModel)
        .outerjoin(snapshot, snapshot.event_id == EventModel.id)
        .where(
            EventModel.status == "SETTLED",
            EventModel.event_date >= window.periods[0].start,
            EventModel.event_date < window.current.end,
        )
        .cte("dashboard_events")
    )
    current = select(base).where(base.c.event_date >= window.current.start).cte("current_events")

    def totals(source: Any = base) -> list[ColumnElement[Any]]:
        return [
            func.count().label("events"),
            *(cast(func.sum(source.c[name]), String).label(name) for name in _AMOUNTS),
        ]

    month = func.date_trunc("month", base.c.event_date)
    monthly = select(func.to_char(month, "YYYY-MM").label("period"), *totals()).group_by(month)
    # Las sumas financieras siempre parten de una fila por evento, sin unir extras.
    # Clave normalizada (espacios recortados y colapsados, sin distinguir mayúsculas); el nombre
    # mostrado es la variante más frecuente del grupo (empate: la menor), con su capitalización.
    cleaned = func.trim(func.regexp_replace(current.c.district, r"\s+", " ", "g"))
    districts = (
        select(func.mode().within_group(cleaned).label("district"), *totals(current))
        .select_from(current)
        .group_by(func.lower(cleaned))
    )
    packages = (
        select(PackageModel.id.label("id"), PackageModel.name, func.count().label("events"))
        .select_from(current)
        .join(QuoteModel, QuoteModel.id == current.c.quote_id)
        .join(PackageModel, PackageModel.id == QuoteModel.package_id)
        .group_by(PackageModel.id, PackageModel.name)
    )
    themes = (
        select(
            ThemeModel.id.label("id"),
            ThemeModel.name.label("name"),
            func.count().label("events"),
        )
        .select_from(current)
        .join(QuoteModel, QuoteModel.id == current.c.quote_id)
        .outerjoin(ThemeModel, ThemeModel.id == QuoteModel.theme_id)
        .group_by(ThemeModel.id, ThemeModel.name)
    )
    extras = (
        select(
            ExtraModel.id.label("id"),
            ExtraModel.name,
            func.sum(QuoteExtraModel.quantity).label("times_hired"),
        )
        .select_from(current)
        .join(QuoteExtraModel, QuoteExtraModel.quote_id == current.c.quote_id)
        .join(ExtraModel, ExtraModel.id == QuoteExtraModel.extra_id)
        .group_by(ExtraModel.id, ExtraModel.name)
    )
    invalid = or_(
        *(
            or_(base.c[name] < 0, cast(base.c[name], String).in_(("NaN", "Infinity", "-Infinity")))
            for name in _AMOUNTS
        )
    )
    missing_filter = base.c.snapshot_id.is_(None)
    return select(
        select(func.count())
        .select_from(base)
        .where(missing_filter)
        .scalar_subquery()
        .label("missing"),
        select(func.array_agg(base.c.id))
        .where(missing_filter)
        .scalar_subquery()
        .label("missing_event_ids"),
        select(func.count()).select_from(base).where(invalid).scalar_subquery().label("invalid"),
        select(func.array_agg(base.c.id))
        .where(invalid)
        .scalar_subquery()
        .label("invalid_event_ids"),
        _collection(monthly).label("months"),
        _collection(packages).label("packages"),
        _collection(themes).label("themes"),
        _collection(extras).label("extras"),
        _collection(districts).label("districts"),
    )


def _totals(row: Mapping[str, Any]) -> FinancialTotals:
    amounts = [Money(Decimal(row[name])) for name in _AMOUNTS]
    return FinancialTotals(row["events"], *amounts)


class SqlAlchemyDashboardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_dashboard(self, window: DashboardWindow) -> DashboardReadData:
        row = (await self._session.execute(dashboard_statement(window))).one()
        if row.missing or row.invalid:
            logger.warning(
                "dashboard_data_inconsistent",
                period=window.current.label,
                missing_snapshots=row.missing,
                invalid_snapshots=row.invalid,
                missing_event_ids=sorted(str(event_id) for event_id in row.missing_event_ids or ()),
                invalid_event_ids=sorted(str(event_id) for event_id in row.invalid_event_ids or ()),
            )
            raise FinancialDataInconsistentError(
                "Existen eventos liquidados sin instantánea o con importes contables inválidos."
            )
        return DashboardReadData(
            tuple(MonthlyTotals(item["period"], _totals(item)) for item in row.months),
            tuple(
                PackageMetric(UUID(item["id"]), item["name"], item["events"])
                for item in row.packages
            ),
            tuple(
                ThemeMetric(
                    UUID(item["id"]) if item["id"] is not None else None,
                    item["name"],
                    item["events"],
                )
                for item in row.themes
            ),
            tuple(
                ExtraRanking(UUID(item["id"]), item["name"], item["times_hired"])
                for item in row.extras
            ),
            tuple(DistrictTotals(item["district"], _totals(item)) for item in row.districts),
        )
