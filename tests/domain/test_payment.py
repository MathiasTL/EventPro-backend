"""Tests de dominio de la entidad Payment (máquina de estados)."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.entities.payment import (
    AuditStatus,
    Payment,
    PaymentConcept,
    PaymentMethod,
    ValidationStatus,
)
from app.domain.exceptions.resource_exceptions import (
    InvalidPaymentStateError,
    ValidationError,
)
from app.domain.value_objects.money import Money


def _advance() -> Payment:
    return Payment(
        quote_id=uuid4(),
        concept=PaymentConcept.ADVANCE,
        payment_method=PaymentMethod.YAPE,
        amount=Money(Decimal("100.00")),
        evidence_path="evidence/x.png",
    )


def _balance() -> Payment:
    event_id = uuid4()
    payment = Payment(
        quote_id=uuid4(),
        event_id=event_id,
        concept=PaymentConcept.BALANCE,
        payment_method=PaymentMethod.CASH,
        amount=Money(Decimal("980.50")),
        evidence_path="evidence/y.jpg",
        validation_status=ValidationStatus.VERIFIED,
        registered_by_user_id=uuid4(),
        audit_status=AuditStatus.UNREVIEWED,
    )
    return payment


def test_verify_advance() -> None:
    payment = _advance()
    user_id = uuid4()
    payment.verify(verified_by=user_id, event_id=uuid4())
    assert payment.validation_status == ValidationStatus.VERIFIED
    assert payment.verified_by_user_id == user_id


def test_verify_requires_pending() -> None:
    payment = _advance()
    payment.verify(verified_by=uuid4())
    with pytest.raises(InvalidPaymentStateError):
        payment.verify(verified_by=uuid4())


def test_reject_requires_reason() -> None:
    payment = _advance()
    with pytest.raises(ValidationError):
        payment.reject(reason="  ")
    payment.reject(reason="Captura ilegible")
    assert payment.validation_status == ValidationStatus.REJECTED


def test_reject_from_requires_manual_approval() -> None:
    payment = _advance()
    payment.require_manual_approval("CONFLICT")
    payment.reject(reason="Monto no coincide")
    assert payment.validation_status == ValidationStatus.REJECTED


def test_balance_audit_transitions() -> None:
    payment = _balance()
    with pytest.raises(ValidationError):
        payment.audit(status=AuditStatus.FLAGGED, audited_by=uuid4(), notes=None)
    payment.audit(status=AuditStatus.FLAGGED, audited_by=uuid4(), notes="Monto distinto")
    assert payment.audit_status == AuditStatus.FLAGGED
    payment.audit(status=AuditStatus.REVIEWED, audited_by=uuid4(), notes=None)
    assert payment.audit_status == AuditStatus.REVIEWED


def test_balance_cannot_use_verify() -> None:
    payment = _balance()
    with pytest.raises(InvalidPaymentStateError):
        payment.verify(verified_by=uuid4())


def test_refund_flow() -> None:
    payment = _advance()
    payment.require_manual_approval("THRESHOLD_EXCEEDED")
    payment.mark_refund_pending()
    payment.confirm_refund()
    assert payment.validation_status == ValidationStatus.REFUNDED


def test_advance_has_no_audit() -> None:
    payment = _advance()
    with pytest.raises(InvalidPaymentStateError):
        payment.audit(status=AuditStatus.REVIEWED, audited_by=uuid4())
