"""Tablas ``inventory_reservations`` y ``crew_assignments`` (motor de disponibilidad, E3).

Su DDL vive en ``alembic/versions/0001_initial_schema.py``. Estos modelos habilitan
la verificación de disponibilidad (RF-09, RF-10, RF-20).

Convención de ventanas: las reservas se construyen desde ``event_date``/``start_time``
del evento **normalizadas a UTC** (ver ``TimeWindow.from_schedule``). Así las
comparaciones de solape son exactas e independientes de la zona horaria de la sesión
de base de datos.
"""

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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.adapters.secondary.persistence.models.base import Base
from app.infrastructure.adapters.secondary.persistence.models.catalog_models import (
    CrewModel,
    InventoryItemModel,
)


class InventoryReservationModel(Base):
    """Reserva de unidades de inventario para un evento y una ventana de tiempo."""

    __tablename__ = "inventory_reservations"
    __table_args__ = (
        Index("ix_inventory_reservations_event_id", "event_id"),
        Index(
            "ix_inventory_reservations_item_window",
            "inventory_item_id",
            "starts_at",
            "ends_at",
        ),
        CheckConstraint("quantity > 0", name="ck_inventory_reservations_quantity_positive"),
        CheckConstraint("ends_at > starts_at", name="ck_inventory_reservations_window"),
        CheckConstraint(
            "status IN ('ACTIVE', 'RELEASED')", name="ck_inventory_reservations_status"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    event_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("events.id"), nullable=False
    )
    inventory_item_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("inventory_items.id"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'ACTIVE'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    inventory_item: Mapped[InventoryItemModel] = relationship(lazy="selectin")


class CrewAssignmentModel(Base):
    """Asignación de un elenco a un evento, con el intervalo de tránsito aplicado."""

    __tablename__ = "crew_assignments"
    __table_args__ = (
        UniqueConstraint("event_id", "crew_id", name="uq_crew_assignments_event_crew"),
        CheckConstraint(
            "transit_interval_minutes >= 0",
            name="ck_crew_assignments_transit_interval_non_negative",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    event_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("events.id"), nullable=False
    )
    crew_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("crews.id"), nullable=False, index=True
    )
    transit_interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transit_interval_overridden: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    crew: Mapped[CrewModel] = relationship(lazy="selectin")
