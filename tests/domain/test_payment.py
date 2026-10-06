from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.entities.payment import (
    Payment,
    PaymentAuditStatus,
    PaymentConcept,
    PaymentMethod,
    PaymentValidationStatus,
)
from app.domain.exceptions.payment_exceptions import InvalidPaymentStateError
from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.money import Money


def _advance(**changes) -> Payment:
    values = {
        "quote_id": uuid4(),
        "concept": PaymentConcept.ADVANCE,
        "payment_method": PaymentMethod.YAPE,
        "amount": Money(Decimal("100.00")),
        "evidence_path": "evidence/receipt.png",
    }
    values.update(changes)
    return Payment(**values)


def _in_situ(**changes) -> Payment:
    values = {
        "quote_id": uuid4(),
        "event_id": uuid4(),
        "concept": PaymentConcept.BALANCE,
        "payment_method": PaymentMethod.CASH,
        "amount": Money(Decimal("980.50")),
        "evidence_path": "evidence/screen.png",
        "validation_status": PaymentValidationStatus.VERIFIED,
        "registered_by_user_id": uuid4(),
        "audit_status": PaymentAuditStatus.UNREVIEWED,
    }
    values.update(changes)
    return Payment(**values)


def test_advance_verify_updates_state_and_user() -> None:
    payment = _advance()
    user_id = uuid4()
    payment.verify(verified_by_user_id=user_id, event_id=None, verified_at=datetime.now(UTC))
    assert payment.validation_status == PaymentValidationStatus.VERIFIED
    assert payment.verified_by_user_id == user_id
    assert payment.event_id is None


def test_advance_reject_requires_reason() -> None:
    payment = _advance()
    with pytest.raises(ValidationError):
        payment.reject(reason="  ", rejected_at=datetime.now(UTC))
    payment.reject(reason="Monto incompleto", rejected_at=datetime.now(UTC))
    assert payment.validation_status == PaymentValidationStatus.REJECTED


def test_advance_state_machine_blocks_invalid_refund() -> None:
    payment = _advance()
    with pytest.raises(InvalidPaymentStateError):
        payment.confirm_refund()


def test_in_situ_audit_requires_notes_for_flagged() -> None:
    payment = _in_situ()
    with pytest.raises(ValidationError):
        payment.audit(
            audited_by_user_id=uuid4(),
            status=PaymentAuditStatus.FLAGGED,
            notes=None,
        )


def test_in_situ_audit_transitions() -> None:
    payment = _in_situ()
    user_id = uuid4()
    payment.audit(
        audited_by_user_id=user_id,
        status=PaymentAuditStatus.FLAGGED,
        notes="Monto de la captura no coincide",
    )
    assert payment.audit_status == PaymentAuditStatus.FLAGGED
    assert payment.audited_by_user_id == user_id
    assert payment.audit_notes == "Monto de la captura no coincide"
