"""Cableado real de cotizaciones, clientes y ciclo de vida sobre la sesión de la petición."""

from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.clients.find_clients import FindClientsUseCase
from app.application.use_cases.clients.get_client import GetClientUseCase
from app.application.use_cases.quote.cancel_quote import CancelQuoteUseCase
from app.application.use_cases.quote.create_quote import CreateQuoteUseCase
from app.application.use_cases.quote.expire_due_quotes import ExpireDueQuotesUseCase
from app.application.use_cases.quote.get_quote import GetQuoteUseCase
from app.application.use_cases.quote.list_quotes import ListQuotesUseCase
from app.application.use_cases.quote.pay_advance import PayAdvanceUseCase
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


def test_quote_lifecycle_providers_are_real_and_bound_to_the_session():
    session = AsyncMock(spec=AsyncSession)
    pay = containers.get_pay_advance_use_case(session)
    cancel = containers.get_cancel_quote_use_case(session)
    assert isinstance(pay, PayAdvanceUseCase)
    assert isinstance(cancel, CancelQuoteUseCase)
    assert pay._quotes._session is session
    assert cancel._quotes._session is session
    transaction = containers.build_bot_transaction(session)
    assert isinstance(transaction.pay_advance, PayAdvanceUseCase)
    assert transaction.pay_advance._quotes._session is session


def test_client_providers_are_real_and_scoped_to_the_request():
    session = AsyncMock(spec=AsyncSession)
    find = containers.get_find_clients_use_case(session)
    detail = containers.get_client_use_case(session)
    assert isinstance(find, FindClientsUseCase)
    assert isinstance(detail, GetClientUseCase)
    assert find._clients._session is session
    assert detail._clients._session is session
