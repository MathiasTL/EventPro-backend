"""Ejecuta la suite de contrato de ``quote_ports_contract`` contra los fakes (spec 08, 2.6).

Esta prueba es parte del contrato: cada responsable replica estas subclases con su
implementación real, ``make_port`` y los ganchos que dependen de una base de integración.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from app.application.ports.input.client_read_port import IFindClientsPort, IGetClientPort
from app.application.ports.input.quote_create_port import ICreateQuotePort
from app.application.ports.input.quote_expiry_port import IExpireDueQuotesPort
from app.application.ports.input.quote_lifecycle_port import ICancelQuotePort, IPayAdvancePort
from app.application.ports.input.quote_read_port import IGetQuotePort, IListQuotesPort
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
    FakeScenario,
)

from .quote_ports_contract import (
    CancelQuoteContract,
    CreateQuoteContract,
    ExpireDueQuotesContract,
    FindClientsContract,
    GetClientContract,
    GetQuoteContract,
    ListQuotesContract,
    PayAdvanceContract,
)

NOW = datetime(2026, 10, 7, 15, 0, tzinfo=UTC)


class FrozenClock:
    def utcnow(self) -> datetime:
        return NOW


class FakeContractHooks:
    """Ganchos de los fakes: un almacén y un reloj nuevos por prueba."""

    def setup_method(self) -> None:
        self.store = FakeQuoteStore()
        self.clock = FrozenClock()

    def seed_quote(
        self,
        status: QuoteStatus,
        *,
        payment_in_verification: bool = False,
        age: timedelta = timedelta(0),
        client_id: UUID | None = None,
        event_date: date | None = None,
    ) -> UUID:
        return self.store.seed_quote(
            status,
            payment_in_verification=payment_in_verification,
            client_id=client_id,
            sent_at=self.clock.utcnow() - age,
            event_date=event_date or date(2026, 10, 15),
        )

    def seed_client(self, phone: str, full_name: str) -> UUID:
        return self.store.add_client(phone, full_name).id

    def arrange(self, port: Any, scenario: FakeScenario) -> None:
        port.scenario = scenario

    def quote_count(self) -> int:
        return len(self.store.quotes())

    def assert_nothing_committed(self) -> None:
        # Los fakes no reciben sesión ni confirman: lo cumplen por construcción
        # (``test_fakes_take_no_session_and_no_messaging_dependency`` lo fija).
        assert not hasattr(self.store, "commit")


class TestFakeCreateQuote(FakeContractHooks, CreateQuoteContract):
    def make_port(self) -> ICreateQuotePort:
        return FakeCreateQuote(self.store, clock=self.clock)


class TestFakeGetQuote(FakeContractHooks, GetQuoteContract):
    def make_port(self) -> IGetQuotePort:
        return FakeGetQuote(self.store, clock=self.clock)


class TestFakeListQuotes(FakeContractHooks, ListQuotesContract):
    def make_port(self) -> IListQuotesPort:
        return FakeListQuotes(self.store, clock=self.clock)


class TestFakePayAdvance(FakeContractHooks, PayAdvanceContract):
    def make_port(self) -> IPayAdvancePort:
        return FakePayAdvance(self.store, clock=self.clock)


class TestFakeCancelQuote(FakeContractHooks, CancelQuoteContract):
    def make_port(self) -> ICancelQuotePort:
        return FakeCancelQuote(self.store, clock=self.clock)


class TestFakeExpireDueQuotes(FakeContractHooks, ExpireDueQuotesContract):
    def make_port(self) -> IExpireDueQuotesPort:
        return FakeExpireDueQuotes(self.store, clock=self.clock)


class TestFakeFindClients(FakeContractHooks, FindClientsContract):
    def make_port(self) -> IFindClientsPort:
        return FakeFindClients(self.store, clock=self.clock)


class TestFakeGetClient(FakeContractHooks, GetClientContract):
    def make_port(self) -> IGetClientPort:
        return FakeGetClient(self.store, clock=self.clock)
