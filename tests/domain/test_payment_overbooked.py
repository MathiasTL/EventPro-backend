"""Pruebas del agregado Payment para la resolución de sobrecupo (RF-20)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.entities.payment import (
    InvalidPaymentStateError,
    Payment,
    PaymentConcept,
    PaymentMethod,
    PaymentValidationStatus,
)
from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.money import Money


def _payment(status: PaymentValidationStatus) -> Payment:
    return Payment(
        quote_id=uuid4(),
        concept=PaymentConcept.ADVANCE,
        payment_method=PaymentMethod.YAPE,
        amount=Money(Decimal("100.00")),
        evidence_path="uploads/advance.jpg",
        validation_status=status,
    )


def test_approve_overbooked_requires_manual_approval_state() -> None:
    payment = _payment(PaymentValidationStatus.PENDING_VERIFICATION)
    with pytest.raises(InvalidPaymentStateError):
        payment.approve_overbooked(
            verified_by_user_id=uuid4(), event_id=None, approved_at=datetime.now(UTC)
        )


def test_approve_overbooked_moves_to_verified_and_records_event() -> None:
    payment = _payment(PaymentValidationStatus.REQUIRES_MANUAL_APPROVAL)
    user_id, event_id = uuid4(), uuid4()
    payment.approve_overbooked(
        verified_by_user_id=user_id, event_id=event_id, approved_at=datetime.now(UTC)
    )
    assert payment.validation_status is PaymentValidationStatus.VERIFIED
    assert payment.verified_by_user_id == user_id
    assert payment.event_id == event_id


def test_approve_overbooked_rejects_naive_timestamp() -> None:
    payment = _payment(PaymentValidationStatus.REQUIRES_MANUAL_APPROVAL)
    with pytest.raises(ValidationError):
        payment.approve_overbooked(
            verified_by_user_id=uuid4(), event_id=None, approved_at=datetime(2026, 12, 24, 20, 0)
        )


def test_mark_refund_pending_from_manual_approval() -> None:
    payment = _payment(PaymentValidationStatus.REQUIRES_MANUAL_APPROVAL)
    payment.mark_refund_pending()
    assert payment.validation_status is PaymentValidationStatus.REFUND_PENDING
