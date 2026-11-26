"""EnsureQuoteEvent y VerifyPaymentUseCase: creación del evento al verificar el adelanto."""

from datetime import UTC, date, datetime, time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.dtos.availability_dto import AvailabilityResult, AvailabilityStatus
from app.application.dtos.payment_dto import VerifyPaymentInput
from app.application.use_cases.contract.ensure_quote_event import EnsureQuoteEvent
from app.application.use_cases.payment.verify_payment import VerifyPaymentUseCase
from app.domain.entities.payment import PaymentConcept
from app.domain.entities.quote import Quote, QuoteSource, QuoteStatus
from app.domain.exceptions.resource_exceptions import ResourceInUseError, ValidationError
from app.domain.value_objects.liquidation import Liquidation
from app.domain.value_objects.money import Money

NOW = datetime(2026, 11, 1, tzinfo=UTC)


def quote(status: QuoteStatus = QuoteStatus.PAYMENT_STARTED) -> Quote:
    zero, total = Money.zero(), Money(Decimal("100"))
    return Quote(
        client_id=uuid4(),
        source=QuoteSource.WHATSAPP,
        event_date=date(2027, 1, 10),
        event_time=time(22),
        location_address="Av. Principal 123",
        location_district="Lima",
        package_id=uuid4(),
        liquidation=Liquidation(
            services_subtotal=total,
            mobility_amount=zero,
            total_amount=total,
            advance_amount=Money(Decimal("10")),
            pending_balance=Money(Decimal("90")),
            balance_services=Money(Decimal("90")),
            balance_mobility=zero,
        ),
        sent_at=NOW,
        expires_at=NOW.replace(year=2028),
        status=status,
    )


class FakeStore:
    def __init__(self, quote_: Quote, existing=None) -> None:
        self.quote, self.existing, self.added, self.saved = quote_, existing, [], 0

    async def lock_quote(self, quote_id):
        return self.quote

    async def existing_event(self, quote_id):
        return self.existing

    async def add_event(self, quote_, event_id, window, requirements):
        self.added.append((event_id, window, requirements))

    async def save_quote(self, quote_):
        self.saved += 1


def build(store: FakeStore, status=AvailabilityStatus.AVAILABLE) -> EnsureQuoteEvent:
    catalog = SimpleNamespace(
        get_package=AsyncMock(return_value=SimpleNamespace(duration_minutes=90)),
        get_inventory_requirements=AsyncMock(return_value=[]),
    )
    availability = SimpleNamespace(
        check_availability=AsyncMock(return_value=AvailabilityResult(status))
    )
    return EnsureQuoteEvent(store, catalog, availability)  # type: ignore[arg-type]


async def test_creates_event_and_converts_quote() -> None:
    store = FakeStore(quote())
    event_id = await build(store).ensure_event(store.quote.id)
    assert event_id is not None and store.added[0][0] == event_id
    assert store.quote.status is QuoteStatus.CONVERTED and store.saved == 1
    assert store.added[0][1].duration_minutes == 90


async def test_reuses_existing_event_without_adding_another() -> None:
    existing = uuid4()
    store = FakeStore(quote(), existing=(existing, "AWAITING_SIGNATURE"))
    assert await build(store).ensure_event(store.quote.id) == existing
    assert store.added == [] and store.quote.status is QuoteStatus.CONVERTED


async def test_conflict_creates_nothing() -> None:
    store = FakeStore(quote())
    assert await build(store, AvailabilityStatus.CONFLICT).ensure_event(store.quote.id) is None
    assert store.added == [] and store.quote.status is QuoteStatus.PAYMENT_STARTED


async def test_quote_not_waiting_for_payment_is_rejected() -> None:
    store = FakeStore(quote(QuoteStatus.EXPIRED))
    with pytest.raises(ResourceInUseError):
        await build(store).ensure_event(store.quote.id)


async def test_non_advance_without_event_id_still_requires_it() -> None:
    payment = SimpleNamespace(
        id=uuid4(), quote_id=uuid4(), concept=PaymentConcept.BALANCE, validation_status=None
    )
    repo = SimpleNamespace(get_by_id=AsyncMock(return_value=payment), save=AsyncMock())
    events = SimpleNamespace(ensure_event=AsyncMock())
    use_case = VerifyPaymentUseCase(repo, SimpleNamespace(), events)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        await use_case.execute(
            VerifyPaymentInput(
                payment_id=payment.id, action="VERIFIED", verified_by_user_id=uuid4()
            )
        )
    events.ensure_event.assert_not_awaited()
