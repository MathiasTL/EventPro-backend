"""Tests de casos de uso de pagos con puertos falsos (E5)."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.application.dtos.payment_dto import (
    CreateAdvancePaymentDTO,
    PaymentFilterDTO,
    PaymentReadDTO,
    RefundPaymentDTO,
    VerifyPaymentDTO,
)
from app.application.use_cases import payments as uc
from app.domain.entities.payment import (
    Payment,
    PaymentConcept,
    PaymentMethod,
    ValidationStatus,
)
from app.domain.exceptions.resource_exceptions import (
    ResourceInUseError,
    ResourceNotFoundError,
    ValidationError,
)


class FakePaymentRepository:
    def __init__(self) -> None:
        self._items: dict[UUID, Payment] = {}

    async def save(self, payment: Payment) -> Payment:
        self._items[payment.id] = payment
        return payment

    async def get(self, payment_id: UUID) -> Payment | None:
        return self._items.get(payment_id)

    async def list(self, filters: PaymentFilterDTO) -> Sequence[PaymentReadDTO]:
        return []

    async def count(self, filters: PaymentFilterDTO) -> int:
        return len(self._items)

    async def find_active_advance(self, quote_id: UUID) -> Payment | None:
        for item in self._items.values():
            if (
                item.quote_id == quote_id
                and item.concept == PaymentConcept.ADVANCE
                and item.validation_status
                in (
                    ValidationStatus.PENDING_VERIFICATION,
                    ValidationStatus.REQUIRES_MANUAL_APPROVAL,
                    ValidationStatus.VERIFIED,
                )
            ):
                return item
        return None


async def test_register_and_duplicate() -> None:
    repo = FakePaymentRepository()
    use_case = uc.RegisterAdvancePaymentUseCase(repo)
    quote_id = uuid4()
    result = await use_case.execute(
        CreateAdvancePaymentDTO(
            quote_id=quote_id,
            payment_method=PaymentMethod.YAPE,
            amount=Decimal("150.00"),
            evidence_path="evidence/receipt.png",
        )
    )
    assert result.validation_status == ValidationStatus.PENDING_VERIFICATION
    with pytest.raises(ResourceInUseError):
        await use_case.execute(
            CreateAdvancePaymentDTO(
                quote_id=quote_id,
                payment_method=PaymentMethod.PLIN,
                amount=Decimal("150.00"),
                evidence_path="evidence/receipt2.png",
            )
        )


async def test_verify_approve() -> None:
    repo = FakePaymentRepository()
    register = uc.RegisterAdvancePaymentUseCase(repo)
    created = await register.execute(
        CreateAdvancePaymentDTO(
            quote_id=uuid4(),
            payment_method=PaymentMethod.BANK_TRANSFER,
            amount=Decimal("200.00"),
            evidence_path="evidence/receipt.pdf",
        )
    )
    verify = uc.VerifyPaymentUseCase(repo)
    result = await verify.execute(
        created.payment_id,
        VerifyPaymentDTO(status=ValidationStatus.VERIFIED),
        verified_by=uuid4(),
    )
    assert result.validation_status == ValidationStatus.VERIFIED


async def test_verify_reject_requires_reason() -> None:
    repo = FakePaymentRepository()
    register = uc.RegisterAdvancePaymentUseCase(repo)
    created = await register.execute(
        CreateAdvancePaymentDTO(
            quote_id=uuid4(),
            payment_method=PaymentMethod.YAPE,
            amount=Decimal("100.00"),
            evidence_path="evidence/receipt.png",
        )
    )
    verify = uc.VerifyPaymentUseCase(repo)
    with pytest.raises(ValidationError):
        await verify.execute(
            created.payment_id,
            VerifyPaymentDTO(status=ValidationStatus.REJECTED, rejection_reason=None),
            verified_by=uuid4(),
        )


async def test_get_missing_raises() -> None:
    repo = FakePaymentRepository()
    with pytest.raises(ResourceNotFoundError):
        await uc.GetPaymentUseCase(repo).execute(uuid4())


async def test_refund_requires_state() -> None:
    repo = FakePaymentRepository()
    register = uc.RegisterAdvancePaymentUseCase(repo)
    created = await register.execute(
        CreateAdvancePaymentDTO(
            quote_id=uuid4(),
            payment_method=PaymentMethod.YAPE,
            amount=Decimal("50.00"),
            evidence_path="evidence/receipt.png",
        )
    )
    with pytest.raises(ValidationError):
        await uc.RefundPaymentUseCase(repo).execute(
            created.payment_id,
            RefundPaymentDTO(refund_method=PaymentMethod.YAPE),
        )
