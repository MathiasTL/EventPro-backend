"""Mapeo de la tabla contracts existente desde 0001."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.adapters.secondary.persistence.models.base import Base


class ContractModel(Base):
    __tablename__ = "contracts"
    __table_args__ = (
        Index("ix_contracts_event_id", "event_id"),
        Index(
            "uq_contracts_event_active",
            "event_id",
            unique=True,
            postgresql_where=text("status <> 'VOIDED'"),
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'ISSUED', 'SIGNED', 'VOIDED')", name="ck_contracts_status"
        ),
        CheckConstraint("otp_attempts >= 0", name="ck_contracts_otp_attempts_non_negative"),
        CheckConstraint(
            "status NOT IN ('ISSUED', 'SIGNED') OR pdf_storage_path IS NOT NULL",
            name="ck_contracts_pdf_path_required",
        ),
        CheckConstraint(
            "status <> 'SIGNED' OR (signed_at IS NOT NULL AND "
            "sealed_pdf_storage_path IS NOT NULL AND sealed_pdf_sha256 IS NOT NULL)",
            name="ck_contracts_signed_requires_seal",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    contract_number: Mapped[str] = mapped_column(String(30), unique=True)
    event_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("events.id"))
    pdf_storage_path: Mapped[str | None] = mapped_column(String(255))
    signature_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    signature_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    otp_hash: Mapped[str | None] = mapped_column(String(255))
    otp_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    otp_attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    otp_last_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    otp_window_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    otp_request_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    signature_image_path: Mapped[str | None] = mapped_column(String(255))
    signer_ip: Mapped[str | None] = mapped_column(String(45))
    signer_user_agent: Mapped[str | None] = mapped_column(String(255))
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sealed_pdf_storage_path: Mapped[str | None] = mapped_column(String(255))
    sealed_pdf_sha256: Mapped[str | None] = mapped_column(CHAR(64))
    is_timestamped: Mapped[bool] = mapped_column(Boolean, server_default=text("FALSE"))
    status: Mapped[str] = mapped_column(String(30), server_default=text("'DRAFT'"))
    is_manual_mode: Mapped[bool] = mapped_column(Boolean, server_default=text("FALSE"))
    custom_clauses: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )
