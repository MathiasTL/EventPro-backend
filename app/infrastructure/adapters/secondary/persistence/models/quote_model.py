"""Tablas quotes y quote_extras (0001_initial_schema + manual_request_hash de 0003)."""

from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.adapters.secondary.persistence.models.base import Base


class QuoteModel(Base):
    __tablename__ = "quotes"
    __table_args__ = (
        CheckConstraint("source IN ('WHATSAPP', 'MANUAL')", name="ck_quotes_source"),
        CheckConstraint(
            "status IN ('SENT', 'PAYMENT_STARTED', 'CONVERTED', 'EXPIRED', 'CANCELLED')",
            name="ck_quotes_status",
        ),
        Index("ix_quotes_client_id", "client_id"),
        Index("ix_quotes_event_date", "event_date"),
        Index("ix_quotes_location_district", "location_district"),
        Index("ix_quotes_expires_at", "expires_at"),
        Index("ix_quotes_package_id", "package_id"),
        Index("ix_quotes_theme_id", "theme_id"),
        Index(
            "uq_quotes_manual_request_hash",
            "manual_request_hash",
            unique=True,
            postgresql_where=text("source='MANUAL' AND status IN ('PAYMENT_STARTED','CONVERTED')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    client_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("clients.id"), nullable=False
    )
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'WHATSAPP'")
    )
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    event_time: Mapped[time] = mapped_column(Time, nullable=False)
    location_address: Mapped[str] = mapped_column(String(255), nullable=False)
    location_district: Mapped[str] = mapped_column(String(80), nullable=False)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    package_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("packages.id"), nullable=False
    )
    theme_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("themes.id"), nullable=True
    )
    client_provides_mobility: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )
    # La tabla define DEFAULT 0.00 / 0, pero el ORM omitiría un None y aplicaría ese default.
    # Se declaran sin server_default para persistir NULL, la marca de contingencia por zona.
    calculated_distance_km: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    calculated_transit_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    base_mobility_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, server_default=text("0.00")
    )
    final_mobility_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, server_default=text("0.00")
    )
    mobility_overridden: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )
    mobility_override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    services_subtotal: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    advance_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    pending_balance: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'SENT'"))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    manual_request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    extras: Mapped[list["QuoteExtraModel"]] = relationship(
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="QuoteExtraModel.extra_id",
    )


class QuoteExtraModel(Base):
    __tablename__ = "quote_extras"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_quote_extras_quantity_positive"),
        Index("ix_quote_extras_quote_id", "quote_id"),
        Index("ix_quote_extras_extra_id", "extra_id"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    quote_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False
    )
    extra_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("extras.id"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
