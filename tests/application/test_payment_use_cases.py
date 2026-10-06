from collections.abc import Sequence
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.application.dtos.payment_dto import (
    AuditPaymentInput,
    CreateAdvancePaymentInput,
    PaymentFilters,
    VerifyPaymentInput,
)
from app.application.use_cases.payment.audit_payment import AuditPaymentUseCase
from app.application.use_cases.payment.get_payment import GetPaymentUseCase
from app.application.use_cases.payment.list_payments import ListPaymentsUseCase
from app.application.use_cases.payment.register_advance_payment import RegisterAdvancePaymentUseCase
from app.application.use_cases.payment.verify_payment import VerifyPaymentUseCase
from app.domain.entities.payment import (
    Payment,
    PaymentAuditStatus,
    PaymentConcept,
    PaymentMethod,
    PaymentValidationStatus,
)
from app.domain.exceptions.payment_exceptions import InvalidPaymentStateError
from app.domain.exceptions.resource_exceptions import (
    ResourceInUseError,
    ResourceNotFoundError,
)


class FakePaymentRepository:
    def __init__(self) -> None:
        self._items: list[Payment] = []

    async def save(self, payment: Payment) -> Payment:
        self._items = [p for p in self._items if p.id != payment.id]
        self._items.append(payment)
        return payment

    async def get_by_id(self, payment_id: UUID) -> Payment | None:
        for item in self._items:
            if item.id == payment_id:
                return item
        return None

    async def list_for_payment(self, filters: PaymentFilters) -> Sequence[Payment]:
        return tuple(self._items)

    async def count_for_payment(self, filters: PaymentFilters) -> int:
        return len(self._items)

    async def find_active_advance(self, quote_id: UUID) -> Payment | None:
        for item in self._items:
            if (
                item.concept == PaymentConcept.ADVANCE
                and item.quote_id == quote_id
                and item.validation_status
                in (
                    PaymentValidationStatus.PENDING_VERIFICATION,
                    PaymentValidationStatus.REQUIRES_MANUAL_APPROVAL,
                    PaymentValidationStatus.REFUND_PENDING,
                )
            ):
                return item
        return None


async def test_register_advance_payment_creates_pending_payment() -> None:
    repo = FakePaymentRepository()
    result = await RegisterAdvancePaymentUseCase(repo).execute(
        CreateAdvancePaymentInput(
            quote_id=uuid4(),
            payment_method=PaymentMethod.YAPE,
            amount=Decimal("100.00"),
            evidence_path="evidence/receipt.png",
        )
    )
    assert result.validation_status == PaymentValidationStatus.PENDING_VERIFICATION
    assert result.message == "Comprobante recibido con éxito. En cola de validación."


async def test_register_duplicate_active_advance_raises() -> None:
    repo = FakePaymentRepository()
    quote_id = uuid4()
    await RegisterAdvancePaymentUseCase(repo).execute(
        CreateAdvancePaymentInput(
            quote_id=quote_id,
            payment_method=PaymentMethod.PLIN,
            amount=Decimal("100.00"),
            evidence_path="evidence/receipt.png",
        )
    )
    with pytest.raises(ResourceInUseError):
        await RegisterAdvancePaymentUseCase(repo).execute(
            CreateAdvancePaymentInput(
                quote_id=quote_id,
                payment_method=PaymentMethod.BANK_TRANSFER,
                amount=Decimal("100.00"),
                evidence_path="evidence/receipt.png",
            )
        )


async def test_verify_advance_can_reject_or_approve() -> None:
    repo = FakePaymentRepository()
    reg = RegisterAdvancePaymentUseCase(repo)
    created = await reg.execute(
        CreateAdvancePaymentInput(
            quote_id=uuid4(),
            payment_method=PaymentMethod.YAPE,
            amount=Decimal("120.00"),
            evidence_path="evidence/receipt.png",
        )
    )
    result = await VerifyPaymentUseCase(repo).execute(
        VerifyPaymentInput(
            payment_id=created.payment_id,
            action="VERIFIED",
            verified_by_user_id=uuid4(),
            event_id=None,
        )
    )
    assert result.validation_status == PaymentValidationStatus.VERIFIED


async def test_get_and_list_payments() -> None:
    repo = FakePaymentRepository()
    created = await RegisterAdvancePaymentUseCase(repo).execute(
        CreateAdvancePaymentInput(
            quote_id=uuid4(),
            payment_method=PaymentMethod.CASH,
            amount=Decimal("80.00"),
            evidence_path="evidence/receipt.png",
        )
    )
    detail = await GetPaymentUseCase(repo).execute(created.payment_id)
    assert detail.payment_id == created.payment_id
    page = await ListPaymentsUseCase(repo).execute(PaymentFilters(page=1, page_size=10))
    assert page.total == 1
    with pytest.raises(ResourceNotFoundError):
        await GetPaymentUseCase(repo).execute(uuid4())


async def test_audit_requires_in_situ_payment() -> None:
    repo = FakePaymentRepository()
    advance = await RegisterAdvancePaymentUseCase(repo).execute(
        CreateAdvancePaymentInput(
            quote_id=uuid4(),
            payment_method=PaymentMethod.YAPE,
            amount=Decimal("100.00"),
            evidence_path="evidence/receipt.png",
        )
    )
    with pytest.raises(InvalidPaymentStateError):
        await AuditPaymentUseCase(repo, AsyncMock()).execute(
            AuditPaymentInput(
                payment_id=advance.payment_id,
                audited_by_user_id=uuid4(),
                audit_status=PaymentAuditStatus.REVIEWED,
            )
        )
