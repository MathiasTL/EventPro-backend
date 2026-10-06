from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.entities.audit_log import AUDIT_ACTIONS
from app.infrastructure.adapters.secondary.persistence.models.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_entity", "entity_name", "entity_id"),
        CheckConstraint(
            f"action IN {AUDIT_ACTIONS}",
            name="ck_audit_logs_action",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(50))
    entity_name: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[UUID] = mapped_column(Uuid)
    old_values: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    new_values: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )
