"""Modelos de las reservas y asignaciones ya creadas por el baseline."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.adapters.secondary.persistence.models.base import Base


class CrewAssignmentModel(Base):
    __tablename__ = "crew_assignments"
    __table_args__ = (
        UniqueConstraint("event_id", "crew_id", name="uq_crew_assignments_event_crew"),
        CheckConstraint(
            "transit_interval_minutes >= 0",
            name="ck_crew_assignments_transit_interval_non_negative",
        ),
        Index("ix_crew_assignments_crew_id", "crew_id"),
    )
    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    event_id: Mapped[UUID] = mapped_column(ForeignKey("events.id"))
    crew_id: Mapped[UUID] = mapped_column(ForeignKey("crews.id"))
    transit_interval_minutes: Mapped[int | None] = mapped_column(Integer)
    transit_interval_overridden: Mapped[bool] = mapped_column(Boolean, server_default=text("FALSE"))
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )


class InventoryReservationModel(Base):
    __tablename__ = "inventory_reservations"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_inventory_reservations_quantity_positive"),
        CheckConstraint("ends_at > starts_at", name="ck_inventory_reservations_window"),
        CheckConstraint(
            "status IN ('ACTIVE', 'RELEASED')", name="ck_inventory_reservations_status"
        ),
        Index("ix_inventory_reservations_event_id", "event_id"),
        Index("ix_inventory_reservations_item_window", "inventory_item_id", "starts_at", "ends_at"),
    )
    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    event_id: Mapped[UUID] = mapped_column(ForeignKey("events.id"))
    inventory_item_id: Mapped[UUID] = mapped_column(ForeignKey("inventory_items.id"))
    quantity: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), server_default=text("'ACTIVE'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )
