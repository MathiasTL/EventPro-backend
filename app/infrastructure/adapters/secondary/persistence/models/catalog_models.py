"""Modelos ORM del catálogo y los elencos (épica E3, David).

Incluye paquetes, temáticas, extras, inventario, sus tablas de relación y los
elencos. El motor de disponibilidad (``inventory_reservations`` y
``crew_assignments``) depende de ``events`` y pertenece a la Ola 1.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.adapters.secondary.persistence.models.base import Base

_SERVICE_CATEGORY = "service_category IN ('SHOW', 'DJ', 'DECORATION', 'TENTS')"
_INVENTORY_SERVICE_CATEGORY = "service_category IN ('DECORATION', 'TENTS')"


class PackageModel(Base):
    """Paquete base comercializado (tabla ``packages``)."""

    __tablename__ = "packages"
    __table_args__ = (
        CheckConstraint(_SERVICE_CATEGORY, name="ck_packages_service_category"),
        CheckConstraint("base_price > 0", name="ck_packages_base_price_positive"),
        CheckConstraint("direct_cost >= 0", name="ck_packages_direct_cost_non_negative"),
        CheckConstraint("duration_minutes > 0", name="ck_packages_duration_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    service_category: Mapped[str] = mapped_column(String(30), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    direct_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("60")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))

    themes: Mapped[list[ThemeModel]] = relationship(
        secondary="package_themes", lazy="selectin", order_by="ThemeModel.name"
    )
    inventory_links: Mapped[list[PackageInventoryItemModel]] = relationship(
        lazy="selectin", order_by="PackageInventoryItemModel.id"
    )


class ThemeModel(Base):
    """Temática decorativa (tabla ``themes``)."""

    __tablename__ = "themes"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))


class PackageThemeModel(Base):
    """Relación muchos a muchos paquete ↔ temática compatible."""

    __tablename__ = "package_themes"
    __table_args__ = (UniqueConstraint("package_id", "theme_id", name="uq_package_themes"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    package_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("packages.id"), nullable=False
    )
    theme_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("themes.id"), nullable=False
    )


class ExtraModel(Base):
    """Extra contratable (tabla ``extras``)."""

    __tablename__ = "extras"
    __table_args__ = (
        CheckConstraint("sale_price >= 0", name="ck_extras_sale_price_non_negative"),
        CheckConstraint("direct_cost >= 0", name="ck_extras_direct_cost_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sale_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    direct_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))


class InventoryItemModel(Base):
    """Ítem de inventario físico (tabla ``inventory_items``)."""

    __tablename__ = "inventory_items"
    __table_args__ = (
        CheckConstraint(_INVENTORY_SERVICE_CATEGORY, name="ck_inventory_items_service_category"),
        CheckConstraint("total_stock >= 0", name="ck_inventory_items_total_stock_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    service_category: Mapped[str] = mapped_column(String(30), nullable=False)
    total_stock: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))


class PackageInventoryItemModel(Base):
    """Ítems de inventario que consume cada paquete (`package_inventory_items`)."""

    __tablename__ = "package_inventory_items"
    __table_args__ = (
        UniqueConstraint("package_id", "inventory_item_id", name="uq_package_inventory_items"),
        Index("ix_package_inventory_items_inventory_item_id", "inventory_item_id"),
        CheckConstraint("quantity > 0", name="ck_package_inventory_items_quantity_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    package_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("packages.id", ondelete="CASCADE"),
        nullable=False,
    )
    inventory_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("inventory_items.id"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    inventory_item: Mapped[InventoryItemModel] = relationship(lazy="selectin")


class CrewModel(Base):
    """Elenco o proveedor freelance (tabla ``crews``)."""

    __tablename__ = "crews"
    __table_args__ = (CheckConstraint(_SERVICE_CATEGORY, name="ck_crews_service_category"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=True
    )
    leader_name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    service_category: Mapped[str] = mapped_column(String(30), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))
