"""Cableado real de cotizaciones y clientes; pagos conserva sus proveedores delegados."""

from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.clients.find_clients import FindClientsUseCase
from app.application.use_cases.clients.get_client import GetClientUseCase
from app.application.use_cases.quote.create_quote import CreateQuoteUseCase
from app.application.use_cases.quote.expire_due_quotes import ExpireDueQuotesUseCase
from app.application.use_cases.quote.get_quote import GetQuoteUseCase
from app.application.use_cases.quote.list_quotes import ListQuotesUseCase
from app.infrastructure.adapters.secondary.external_services.fake_quote_use_cases import (
    FakeCancelQuote,
    FakePayAdvance,
)
from app.infrastructure.di import containers


def test_quote_providers_are_real_and_bound_to_the_request_session():
    session = AsyncMock(spec=AsyncSession)
    assert isinstance(containers.get_create_quote_use_case(session), CreateQuoteUseCase)
    assert isinstance(containers.get_quote_use_case(session), GetQuoteUseCase)
    assert isinstance(containers.get_list_quotes_use_case(session), ListQuotesUseCase)
    assert isinstance(containers.get_expire_due_quotes_use_case(session), ExpireDueQuotesUseCase)
    transaction = containers.build_bot_transaction(session)
    assert isinstance(transaction.create_quote, CreateQuoteUseCase)
    assert transaction.create_quote._quotes._session is session


def test_other_owners_keep_their_current_implementations():
    assert isinstance(containers.get_pay_advance_use_case(), FakePayAdvance)
    assert isinstance(containers.get_cancel_quote_use_case(), FakeCancelQuote)


def test_client_providers_are_real_and_scoped_to_the_request():
    session = AsyncMock(spec=AsyncSession)
    find = containers.get_find_clients_use_case(session)
    detail = containers.get_client_use_case(session)
    assert isinstance(find, FindClientsUseCase)
    assert isinstance(detail, GetClientUseCase)
    assert find._clients._session is session
    assert detail._clients._session is session
