"""Tabla events de E6. La FK a quotes se incorporará cuando E1 integre su tabla."""

from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, DateTime, Numeric, String, Text, Time, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.adapters.secondary.persistence.models.base import Base


class EventModel(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint(
            "status IN ('AWAITING_SIGNATURE', 'SCHEDULED', 'AWAITING_BALANCE', "
            "'IN_PROGRESS', 'EXTENDED', 'SETTLED', 'CANCELLED')",
            name="ck_events_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    event_code: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    # Obligatorio y único, deliberadamente sin ForeignKey hasta la integración de E1.
    quote_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, unique=True)
    event_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    district: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    client_observations: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=text("'AWAITING_SIGNATURE'")
    )
    total_services_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    total_mobility_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    final_total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    advance_paid: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, server_default=text("0.00")
    )
    pre_show_balance_paid: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, server_default=text("0.00")
    )
    extra_hours_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, server_default=text("0.00")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    actual_start_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
