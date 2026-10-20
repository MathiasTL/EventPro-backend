"""Límites de fecha del adaptador SQL de la bitácora (regresión del 500 por `to_date`)."""

from datetime import UTC, date, datetime

from sqlalchemy import select

from app.application.dtos.audit_log_dto import AuditLogFilters
from app.infrastructure.adapters.secondary.persistence.audit_log_adapter import (
    SQLAlchemyAuditLogAdapter,
    _day_end,
    _day_start,
)
from app.infrastructure.adapters.secondary.persistence.models.audit_log import (
    AuditLog as AuditLogModel,
)


def _adapter() -> SQLAlchemyAuditLogAdapter:
    """Instancia sin sesión: `_apply_filters` solo construye la sentencia."""
    return object.__new__(SQLAlchemyAuditLogAdapter)


def test_day_end_of_date_max_does_not_overflow() -> None:
    assert _day_end(date.max) == datetime.max.replace(tzinfo=UTC)


def test_day_end_covers_the_whole_day() -> None:
    assert _day_end(date(2026, 10, 31)) == datetime(2026, 11, 1, 0, 0, tzinfo=UTC)


def test_day_start_of_date_max_does_not_overflow() -> None:
    assert _day_start(date.max) == datetime(9999, 12, 31, 0, 0, tzinfo=UTC)


def test_filters_with_max_to_date_build_a_statement() -> None:
    stmt = _adapter()._apply_filters(
        select(AuditLogModel), AuditLogFilters(to_date=date.max, from_date=date.max)
    )
    assert "created_at" in str(stmt.compile())
