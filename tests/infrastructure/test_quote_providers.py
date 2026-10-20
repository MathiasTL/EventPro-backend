from collections.abc import Iterator
from datetime import date, time
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest

from app.application.dtos.quote_dto import ClientInput, CreateQuoteInput
from app.domain.entities.quote import QuoteStatus
from app.infrastructure.adapters.secondary.external_services.fake_quote_use_cases import (
    FakeCancelQuote,
    FakeCreateQuote,
    FakeExpireDueQuotes,
    FakeFindClients,
    FakeGetClient,
    FakeGetQuote,
    FakeListQuotes,
    FakePayAdvance,
    FakeQuoteStore,
)
from app.infrastructure.di import containers

PROVIDERS: dict[str, tuple[Any, type]] = {
    "get_create_quote_use_case": (containers.get_create_quote_use_case, FakeCreateQuote),
    "get_quote_use_case": (containers.get_quote_use_case, FakeGetQuote),
    "get_list_quotes_use_case": (containers.get_list_quotes_use_case, FakeListQuotes),
    "get_expire_due_quotes_use_case": (
        containers.get_expire_due_quotes_use_case,
        FakeExpireDueQuotes,
    ),
    "get_pay_advance_use_case": (containers.get_pay_advance_use_case, FakePayAdvance),
    "get_cancel_quote_use_case": (containers.get_cancel_quote_use_case, FakeCancelQuote),
    "get_find_clients_use_case": (containers.get_find_clients_use_case, FakeFindClients),
    "get_client_use_case": (containers.get_client_use_case, FakeGetClient),
}


@pytest.fixture(autouse=True)
def _fresh_providers() -> Iterator[None]:
    def clear() -> None:
        containers.get_fake_quote_store.cache_clear()
        for provider, _ in PROVIDERS.values():
            provider.cache_clear()

    clear()
    yield
    clear()


def _create_input() -> CreateQuoteInput:
    return CreateQuoteInput(
        package_id=UUID("00000000-0000-0000-0000-0000000000a1"),
        event_date=date(2026, 10, 15),
        event_time=time(21, 30),
        location_address="Av. Benavides 2150",
        location_district="Miraflores",
        client=ClientInput(phone="+51999888777", full_name="Carlos Rodríguez"),
    )


@pytest.mark.parametrize("name", PROVIDERS)
def test_each_provider_returns_the_fake_for_its_port(name: str) -> None:
    provider, fake_class = PROVIDERS[name]
    assert isinstance(provider(), fake_class)


@pytest.mark.parametrize("name", PROVIDERS)
def test_providers_are_cached_singletons(name: str) -> None:
    provider, _ = PROVIDERS[name]
    assert provider() is provider()
    assert containers.get_fake_quote_store() is containers.get_fake_quote_store()
    assert isinstance(containers.get_fake_quote_store(), FakeQuoteStore)


async def test_providers_share_one_store() -> None:
    created = await containers.get_create_quote_use_case().execute(_create_input())
    detail = await containers.get_quote_use_case().execute(created.quote_id)
    client = await containers.get_client_use_case().execute(created.client_id)
    assert detail.quote_id == created.quote_id
    assert client.quotes[0].quote_id == created.quote_id


async def test_create_then_pay_advance_through_the_providers_reaches_payment_started() -> None:
    created = await containers.get_create_quote_use_case().execute(_create_input())
    result = await containers.get_pay_advance_use_case().execute(created.quote_id)
    assert result.status is QuoteStatus.PAYMENT_STARTED
    assert result.advance_amount == Decimal("100.00")
    detail = await containers.get_quote_use_case().execute(created.quote_id)
    assert detail.status is QuoteStatus.PAYMENT_STARTED
