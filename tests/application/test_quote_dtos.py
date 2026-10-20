from dataclasses import fields
from datetime import date, time
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.application.dtos.client_dto import (
    ClientDetailDTO,
    ClientDTO,
    FindClientsFilter,
)
from app.application.dtos.page_dto import PageDTO
from app.application.dtos.quote_dto import (
    ClientInput,
    CreatedQuoteDTO,
    CreateQuoteInput,
    ListQuotesFilter,
    PayAdvanceResultDTO,
    QuoteDetailDTO,
    QuoteExtraInput,
    QuoteListItemDTO,
)
from app.domain.entities.quote import QuoteSource
from app.domain.exceptions.resource_exceptions import ValidationError

PACKAGE_ID = UUID("00000000-0000-0000-0000-0000000000a1")
CLIENT = ClientInput(phone="+51999888777", full_name="Carlos Rodríguez")


def _create_input(**overrides: Any) -> CreateQuoteInput:
    values: dict[str, Any] = {
        "package_id": PACKAGE_ID,
        "event_date": date(2026, 10, 15),
        "event_time": time(21, 30),
        "location_address": "Av. Benavides 2150",
        "location_district": "Miraflores",
        "client": CLIENT,
    }
    values.update(overrides)
    return CreateQuoteInput(**values)


def _names(dto: type) -> set[str]:
    return {field.name for field in fields(dto)}


def test_create_quote_input_requires_exactly_one_client_reference() -> None:
    with pytest.raises(ValidationError):
        _create_input(client=CLIENT, client_id=uuid4())
    with pytest.raises(ValidationError):
        _create_input(client=None, client_id=None)
    assert _create_input(client=CLIENT, client_id=None).client == CLIENT
    existing = uuid4()
    assert _create_input(client=None, client_id=existing).client_id == existing


def test_create_quote_input_defaults_source_to_whatsapp() -> None:
    assert _create_input().source is QuoteSource.WHATSAPP


def test_create_quote_input_rejects_non_positive_extra_quantity() -> None:
    with pytest.raises(ValidationError):
        QuoteExtraInput(extra_id=uuid4(), quantity=0)
    with pytest.raises(ValidationError):
        QuoteExtraInput(extra_id=uuid4(), quantity=-1)
    assert QuoteExtraInput(extra_id=uuid4(), quantity=1).quantity == 1


def test_list_quotes_filter_rejects_inverted_range_and_bad_pagination() -> None:
    with pytest.raises(ValidationError):
        ListQuotesFilter(from_date=date(2026, 10, 31), to_date=date(2026, 10, 1))
    with pytest.raises(ValidationError):
        ListQuotesFilter(page=0)
    with pytest.raises(ValidationError):
        ListQuotesFilter(page_size=0)
    with pytest.raises(ValidationError):
        ListQuotesFilter(page_size=101)
    assert ListQuotesFilter(page_size=100).page_size == 100
    assert ListQuotesFilter(from_date=date(2026, 10, 1), to_date=date(2026, 10, 1)).page == 1


def test_find_clients_filter_rejects_bad_pagination() -> None:
    with pytest.raises(ValidationError):
        FindClientsFilter(page=0)
    with pytest.raises(ValidationError):
        FindClientsFilter(page_size=0)
    with pytest.raises(ValidationError):
        FindClientsFilter(page_size=101)
    assert FindClientsFilter(q="carlos").page_size == 20


def test_dtos_are_frozen() -> None:
    quote_input = _create_input()
    with pytest.raises(AttributeError):
        quote_input.observations = "otra"  # type: ignore[misc]
    page: PageDTO[int] = PageDTO(items=(1,), page=1, page_size=20, total=1)
    with pytest.raises(AttributeError):
        page.total = 2  # type: ignore[misc]
    with pytest.raises(AttributeError):
        FindClientsFilter().page = 2  # type: ignore[misc]


def test_page_dto_carries_items_page_and_total() -> None:
    page = PageDTO(items=(Decimal("1.00"),), page=2, page_size=10, total=11)
    assert (page.items, page.page, page.page_size, page.total) == ((Decimal("1.00"),), 2, 10, 11)


def test_created_quote_dto_fields_match_the_post_quotes_response() -> None:
    assert _names(CreatedQuoteDTO) == {
        "quote_id",
        "client_id",
        "source",
        "availability",
        "services_subtotal",
        "calculated_distance_km",
        "calculated_transit_minutes",
        "final_mobility_amount",
        "total_amount",
        "advance_amount",
        "pending_balance",
        "breakdown",
        "status",
        "sent_at",
        "expires_at",
    }


def test_quote_detail_dto_fields_match_the_get_quote_response() -> None:
    assert _names(QuoteDetailDTO) == {
        "quote_id",
        "client",
        "source",
        "event_date",
        "event_time",
        "location_address",
        "location_district",
        "package",
        "theme",
        "extras",
        "services_subtotal",
        "final_mobility_amount",
        "mobility_overridden",
        "total_amount",
        "advance_amount",
        "pending_balance",
        "status",
        "sent_at",
        "expires_at",
        "observations",
        "payments",
        "event_id",
    }


def test_pay_advance_result_fields_match_the_pay_advance_response() -> None:
    assert _names(PayAdvanceResultDTO) == {
        "quote_id",
        "status",
        "availability",
        "rechecked",
        "advance_amount",
        "payment_deadline",
        "payment_instructions",
    }


def test_client_detail_dto_fields_match_the_get_client_response() -> None:
    assert _names(ClientDetailDTO) == {
        "id",
        "phone",
        "full_name",
        "dni",
        "ruc",
        "created_at",
        "quotes",
    }
    assert _names(ClientDTO) < _names(ClientDetailDTO)


def test_list_item_dto_fields_match_the_get_quotes_response() -> None:
    assert _names(QuoteListItemDTO) == {
        "quote_id",
        "client",
        "event_date",
        "package_name",
        "total_amount",
        "status",
        "expires_at",
    }
