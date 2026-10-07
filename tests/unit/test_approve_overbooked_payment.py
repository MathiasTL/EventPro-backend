"""Pruebas unitarias de ApproveOverbookedPaymentUseCase (RF-20, US-10)."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.dtos.override_dto import (
    ApproveOverbookedInput,
    OverbookedDecision,
)
from app.application.services.audit_service import AuditService
from app.application.use_cases.payment.approve_overbooked_payment import (
    ApproveOverbookedPaymentUseCase,
)
from app.domain.entities.payment import (
    InvalidPaymentStateError,
    Payment,
    PaymentConcept,
    PaymentMethod,
    PaymentValidationStatus,
)
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError
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


def _use_case(
    payment: Payment | None,
) -> tuple[ApproveOverbookedPaymentUseCase, AsyncMock, AsyncMock]:
    payments = AsyncMock()
    payments.get_by_id.return_value = payment
    audit_port = AsyncMock()
    return ApproveOverbookedPaymentUseCase(payments, AuditService(audit_port)), payments, audit_port


def test_approve_overbooked_moves_payment_to_verified() -> None:
    payment = _payment(PaymentValidationStatus.REQUIRES_MANUAL_APPROVAL)
    use_case, payments, audit_port = _use_case(payment)
    event_id = uuid4()
    user_id = uuid4()

    result = asyncio.run(
        use_case.execute(
            ApproveOverbookedInput(
                payment_id=payment.id,
                decision=OverbookedDecision.APPROVE,
                decided_by_user_id=user_id,
                notes="Se contrató elenco adicional freelance.",
                event_id=event_id,
            )
        )
    )

    assert payment.validation_status is PaymentValidationStatus.VERIFIED
    assert payment.verified_by_user_id == user_id
    assert result.event_created_id == event_id
    payments.save.assert_awaited_once()
    entry = audit_port.record.await_args.args[0]
    assert entry.action == "APPROVE_OVERBOOKED_PAYMENT"
    assert entry.entity_id == payment.id
    assert entry.old_values == {"validation_status": "REQUIRES_MANUAL_APPROVAL"}


def test_reject_overbooked_moves_payment_to_refund_pending() -> None:
    payment = _payment(PaymentValidationStatus.REQUIRES_MANUAL_APPROVAL)
    use_case, payments, audit_port = _use_case(payment)

    result = asyncio.run(
        use_case.execute(
            ApproveOverbookedInput(
                payment_id=payment.id,
                decision=OverbookedDecision.REJECT,
                decided_by_user_id=uuid4(),
                notes="Sin elenco de respaldo.",
            )
        )
    )

    assert payment.validation_status is PaymentValidationStatus.REFUND_PENDING
    assert result.event_created_id is None
    payments.save.assert_awaited_once()
    entry = audit_port.record.await_args.args[0]
    assert entry.action == "REJECT_OVERBOOKED_PAYMENT"


def test_missing_payment_raises() -> None:
    use_case, _payments, _audit_port = _use_case(None)
    with pytest.raises(ResourceNotFoundError):
        asyncio.run(
            use_case.execute(
                ApproveOverbookedInput(
                    payment_id=uuid4(),
                    decision=OverbookedDecision.APPROVE,
                    decided_by_user_id=uuid4(),
                )
            )
        )


def test_payment_not_awaiting_manual_approval_raises() -> None:
    payment = _payment(PaymentValidationStatus.PENDING_VERIFICATION)
    use_case, _payments, _audit_port = _use_case(payment)
    with pytest.raises(InvalidPaymentStateError):
        asyncio.run(
            use_case.execute(
                ApproveOverbookedInput(
                    payment_id=payment.id,
                    decision=OverbookedDecision.APPROVE,
                    decided_by_user_id=uuid4(),
                )
            )
        )
