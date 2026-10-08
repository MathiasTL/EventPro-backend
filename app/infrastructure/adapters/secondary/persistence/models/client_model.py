"""Tabla clients (0001_initial_schema): identidad comercial por teléfono."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.adapters.secondary.persistence.models.base import Base


class ClientModel(Base):
    __tablename__ = "clients"
    __table_args__ = (
        CheckConstraint("dni ~ '^[0-9]+$' AND length(dni) = 8", name="ck_clients_dni_format"),
        CheckConstraint("ruc ~ '^[0-9]+$' AND length(ruc) = 11", name="ck_clients_ruc_format"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    phone: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    dni: Mapped[str | None] = mapped_column(String(8), nullable=True)
    ruc: Mapped[str | None] = mapped_column(String(11), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
