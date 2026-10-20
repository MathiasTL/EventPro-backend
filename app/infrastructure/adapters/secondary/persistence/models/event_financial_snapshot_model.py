"""Instantánea contable por evento, insertada junto con SETTLED (PC-09)."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.adapters.secondary.persistence.models.base import Base


class EventFinancialSnapshotModel(Base):
    __tablename__ = "event_financial_snapshots"
    __table_args__ = (
        *(
            CheckConstraint(
                f"{column} >= 0 AND {column} <> 'NaN'::numeric",
                name=f"ck_event_financial_{column}_non_negative",
            )
            for column in (
                "gross_revenue",
                "fixed_packages_cost",
                "fixed_extras_cost",
                "mobility_operational_cost",
            )
        ),
        CheckConstraint(
            "origin IN ('SETTLEMENT', 'LEGACY_BACKFILL')", name="ck_event_financial_origin"
        ),
        CheckConstraint(
            "jsonb_typeof(details) = 'object'", name="ck_event_financial_details_object"
        ),
    )
    event_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("events.id"), primary_key=True
    )
    gross_revenue: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    fixed_packages_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    fixed_extras_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    mobility_operational_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    origin: Mapped[str] = mapped_column(String(20), nullable=False)
    details: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
