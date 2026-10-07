"""Detalle de tiempo extra vinculado a su cobro real de E5."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.adapters.secondary.persistence.models.base import Base


class EventExtensionModel(Base):
    __tablename__ = "event_extensions"
    __table_args__ = (
        CheckConstraint("extra_minutes > 0", name="ck_event_extensions_minutes_positive"),
        CheckConstraint("agreed_rate > 0", name="ck_event_extensions_rate_positive"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    event_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("events.id"), nullable=False, index=True
    )
    payment_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("payments.id"), nullable=False, unique=True
    )
    extra_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    agreed_rate: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
