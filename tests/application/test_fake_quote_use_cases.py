import inspect
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.application.dtos.client_dto import FindClientsFilter
from app.application.dtos.quote_dto import (
    ClientInput,
    CreateQuoteInput,
    ListQuotesFilter,
)
from app.application.ports.input.client_read_port import IFindClientsPort, IGetClientPort
from app.application.ports.input.quote_create_port import ICreateQuotePort
from app.application.ports.input.quote_expiry_port import IExpireDueQuotesPort
from app.application.ports.input.quote_lifecycle_port import ICancelQuotePort, IPayAdvancePort
from app.application.ports.input.quote_read_port import IGetQuotePort, IListQuotesPort
from app.domain.entities.quote import QuoteStatus
from app.domain.exceptions.quote_exceptions import (
    AvailabilityConflictError,
    AvailabilityRejectedError,
    ClientNotFoundError,
    InvalidQuoteStateError,
    QuoteExpiredError,
    QuoteNotFoundError,
    SimultaneousThresholdExceededError,
)
from app.domain.exceptions.resource_exceptions import ValidationError
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

NOW = datetime(2026, 10, 7, 15, 0, tzinfo=UTC)
PACKAGE_ID = UUID("00000000-0000-0000-0000-0000000000a1")
S = FakeScenario


class _FrozenClock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def utcnow(self) -> datetime:
        return self.now


def _create_input(**overrides: Any) -> CreateQuoteInput:
    values: dict[str, Any] = {
        "package_id": PACKAGE_ID,
        "event_date": date(2026, 10, 15),
        "event_time": time(21, 30),
        "location_address": "Av. Benavides 2150",
        "location_district": "Miraflores",
        "client": ClientInput(phone="+51999888777", full_name="Carlos Rodríguez"),
    }
    values.update(overrides)
    return CreateQuoteInput(**values)


def _by_client_id() -> CreateQuoteInput:
    return _create_input(client=None, client_id=uuid4())


# Matriz de la spec 08, sección 2.5: puerto -> escenarios aplicables (además de OK).
APPLICABLE: dict[str, set[FakeScenario]] = {
    "create": {
        S.AVAILABILITY_CONFLICT,
        S.SIMULTANEOUS_THRESHOLD,
        S.VALIDATION_ERROR,
        S.CLIENT_NOT_FOUND,
    },
    "get": {S.QUOTE_NOT_FOUND},
    "list": {S.VALIDATION_ERROR},
    "pay": {
        S.AVAILABILITY_CONFLICT,
        S.SIMULTANEOUS_THRESHOLD,
        S.QUOTE_NOT_FOUND,
        S.QUOTE_EXPIRED,
        S.INVALID_QUOTE_STATE,
    },
    "cancel": {S.QUOTE_NOT_FOUND, S.INVALID_QUOTE_STATE, S.PAYMENT_IN_VERIFICATION},
    "expire": {S.PAYMENT_IN_VERIFICATION},
    "find": set(),
    "client": {S.CLIENT_NOT_FOUND},
}

_RAISED_BY: dict[FakeScenario, type[Exception]] = {
    S.AVAILABILITY_CONFLICT: AvailabilityConflictError,
    S.SIMULTANEOUS_THRESHOLD: SimultaneousThresholdExceededError,
    S.VALIDATION_ERROR: ValidationError,
    S.QUOTE_NOT_FOUND: QuoteNotFoundError,
    S.QUOTE_EXPIRED: QuoteExpiredError,
    S.INVALID_QUOTE_STATE: InvalidQuoteStateError,
    S.PAYMENT_IN_VERIFICATION: InvalidQuoteStateError,  # solo CancelQuote lanza
    S.CLIENT_NOT_FOUND: ClientNotFoundError,
}

# Escenarios que no lanzan en el puerto indicado (ExpireDueQuotes omite y devuelve 0).
_DOES_NOT_RAISE = {("expire", S.PAYMENT_IN_VERIFICATION)}

Factory = Callable[[FakeQuoteStore, _FrozenClock], Any]
Call = Callable[[Any], Awaitable[object]]

PORTS: dict[str, tuple[Factory, Call]] = {
    "create": (lambda s, c: FakeCreateQuote(s, clock=c), lambda f: f.execute(_by_client_id())),
    "get": (lambda s, c: FakeGetQuote(s, clock=c), lambda f: f.execute(uuid4())),
    "list": (lambda s, c: FakeListQuotes(s, clock=c), lambda f: f.execute(ListQuotesFilter())),
    "pay": (lambda s, c: FakePayAdvance(s, clock=c), lambda f: f.execute(uuid4())),
    "cancel": (lambda s, c: FakeCancelQuote(s, clock=c), lambda f: f.execute(uuid4())),
    "expire": (lambda s, c: FakeExpireDueQuotes(s, clock=c), lambda f: f.execute()),
    "find": (lambda s, c: FakeFindClients(s, clock=c), lambda f: f.execute(FindClientsFilter())),
    "client": (lambda s, c: FakeGetClient(s, clock=c), lambda f: f.execute(uuid4())),
}

APPLICABLE_PAIRS = [
    (port, scenario)
    for port, scenarios in APPLICABLE.items()
    for scenario in sorted(scenarios)
    if (port, scenario) not in _DOES_NOT_RAISE
]
INAPPLICABLE_PAIRS = [
    (port, scenario)
    for port in APPLICABLE
    for scenario in FakeScenario
    if scenario is not S.OK and scenario not in APPLICABLE[port]
]


def _build(port: str) -> Any:
    factory, _ = PORTS[port]
    return factory(FakeQuoteStore(), _FrozenClock())


async def test_fake_ids_are_deterministic_across_instances() -> None:
    async def run() -> tuple[UUID, UUID]:
        store = FakeQuoteStore()
        created = await FakeCreateQuote(store, clock=_FrozenClock()).execute(_create_input())
        return created.quote_id, created.client_id

    assert await run() == await run()


@pytest.mark.parametrize(("port", "scenario"), APPLICABLE_PAIRS)
async def test_scenario_matrix_raises_the_mapped_error_for_every_applicable_pair(
    port: str, scenario: FakeScenario
) -> None:
    fake = _build(port)
    fake.scenario = scenario
    with pytest.raises(Exception) as caught:  # noqa: PT011
        await PORTS[port][1](fake)
    assert type(caught.value) is _RAISED_BY[scenario]
    if isinstance(caught.value, AvailabilityRejectedError):
        assert caught.value.alternatives
        assert caught.value.handoff_available is True


@pytest.mark.parametrize(("port", "scenario"), INAPPLICABLE_PAIRS)
def test_inapplicable_scenario_raises_value_error(port: str, scenario: FakeScenario) -> None:
    fake = _build(port)
    with pytest.raises(ValueError, match=scenario.value):
        fake.scenario = scenario


async def test_every_contract_error_is_raised_by_some_fake() -> None:
    raised: set[type[Exception]] = set()
    for port, scenario in APPLICABLE_PAIRS:
        fake = _build(port)
        fake.scenario = scenario
        with pytest.raises(Exception) as caught:  # noqa: PT011
            await PORTS[port][1](fake)
        raised.add(type(caught.value))
    assert raised == {
        AvailabilityConflictError,
        SimultaneousThresholdExceededError,
        QuoteExpiredError,
        InvalidQuoteStateError,
        QuoteNotFoundError,
        ClientNotFoundError,
        ValidationError,
    }


async def test_ok_scenario_is_the_default_and_always_applicable() -> None:
    for port in PORTS:
        assert _build(port).scenario is S.OK


async def test_create_with_client_scenario_that_needs_client_id_is_a_programming_error() -> None:
    fake = FakeCreateQuote(FakeQuoteStore(), clock=_FrozenClock())
    fake.scenario = S.CLIENT_NOT_FOUND
    with pytest.raises(ValueError, match="client_id"):
        await fake.execute(_create_input())


async def test_create_returns_the_api_example_vector() -> None:
    created = await FakeCreateQuote(FakeQuoteStore(), clock=_FrozenClock()).execute(_create_input())
    assert created.services_subtotal == Decimal("1000.00")
    assert created.final_mobility_amount == Decimal("80.50")
    assert created.total_amount == Decimal("1080.50")
    assert created.advance_amount == Decimal("100.00")
    assert created.pending_balance == Decimal("980.50")
    assert created.breakdown.services_balance_due == Decimal("900.00")
    assert created.breakdown.mobility_due == Decimal("80.50")
    assert created.status is QuoteStatus.SENT


async def test_create_then_get_shares_state_through_the_store() -> None:
    store = FakeQuoteStore()
    clock = _FrozenClock()
    created = await FakeCreateQuote(store, clock=clock).execute(
        _create_input(observations="Sin escaleras")
    )
    detail = await FakeGetQuote(store, clock=clock).execute(created.quote_id)
    assert detail.quote_id == created.quote_id
    assert detail.client.id == created.client_id
    assert detail.client.phone == "+51999888777"
    assert detail.total_amount == created.total_amount
    assert detail.observations == "Sin escaleras"
    client = await FakeGetClient(store, clock=clock).execute(created.client_id)
    assert [quote.quote_id for quote in client.quotes] == [created.quote_id]


async def test_pay_advance_after_create_moves_to_payment_started() -> None:
    store = FakeQuoteStore()
    clock = _FrozenClock()
    created = await FakeCreateQuote(store, clock=clock).execute(_create_input())
    result = await FakePayAdvance(store, clock=clock).execute(created.quote_id)
    assert result.status is QuoteStatus.PAYMENT_STARTED
    assert result.payment_deadline == created.expires_at
    assert result.advance_amount == Decimal("100.00")
    assert result.rechecked is False
    detail = await FakeGetQuote(store, clock=clock).execute(created.quote_id)
    assert detail.status is QuoteStatus.PAYMENT_STARTED


async def test_pay_advance_reports_the_configured_rechecked_flag() -> None:
    store = FakeQuoteStore()
    created = await FakeCreateQuote(store, clock=_FrozenClock()).execute(_create_input())
    pay = FakePayAdvance(store, clock=_FrozenClock())
    pay.rechecked = True
    assert (await pay.execute(created.quote_id)).rechecked is True


async def test_pay_advance_derives_rechecked_from_the_quote_age_by_default() -> None:
    store = FakeQuoteStore()
    pay = FakePayAdvance(store, clock=_FrozenClock())
    fresh = store.seed_quote(QuoteStatus.SENT, sent_at=NOW)
    on_the_limit = store.seed_quote(QuoteStatus.SENT, sent_at=NOW - timedelta(minutes=60))
    aged = store.seed_quote(QuoteStatus.SENT, sent_at=NOW - timedelta(minutes=61))
    assert (await pay.execute(fresh)).rechecked is False
    assert (await pay.execute(on_the_limit)).rechecked is False
    assert (await pay.execute(aged)).rechecked is True


async def test_pay_advance_explicit_rechecked_overrides_the_derived_value() -> None:
    store = FakeQuoteStore()
    pay = FakePayAdvance(store, clock=_FrozenClock())
    aged = store.seed_quote(QuoteStatus.SENT, sent_at=NOW - timedelta(hours=2))
    pay.rechecked = False
    assert (await pay.execute(aged)).rechecked is False


async def test_expires_at_is_the_injected_clock_plus_24_hours_in_utc() -> None:
    clock = _FrozenClock(datetime(2026, 11, 2, 9, 30, tzinfo=UTC))
    created = await FakeCreateQuote(FakeQuoteStore(), clock=clock).execute(_create_input())
    assert created.sent_at == clock.now
    assert created.expires_at == clock.now + timedelta(hours=24)
    assert created.sent_at.utcoffset() == timedelta(0)
    assert created.expires_at.utcoffset() == timedelta(0)


async def test_expire_due_quotes_returns_the_configured_due_count() -> None:
    fake = FakeExpireDueQuotes(FakeQuoteStore(), clock=_FrozenClock())
    fake.due_count = 3
    assert await fake.execute() == 3
    assert await fake.execute() == 0


async def test_expire_due_quotes_derives_from_the_store_and_skips_payments_in_verification() -> (
    None
):
    store = FakeQuoteStore()
    clock = _FrozenClock()
    due = store.seed_quote(QuoteStatus.SENT, sent_at=NOW - timedelta(hours=30))
    store.seed_quote(
        QuoteStatus.PAYMENT_STARTED, sent_at=NOW - timedelta(hours=30), payment_in_verification=True
    )
    live = store.seed_quote(QuoteStatus.SENT, sent_at=NOW)
    fake = FakeExpireDueQuotes(store, clock=clock)
    assert await fake.execute() == 1
    assert store.get_quote(due).status is QuoteStatus.EXPIRED
    assert store.get_quote(live).status is QuoteStatus.SENT


async def test_cancel_moves_open_quotes_to_cancelled_and_rejects_terminal_ones() -> None:
    store = FakeQuoteStore()
    cancel = FakeCancelQuote(store, clock=_FrozenClock())
    sent = store.seed_quote(QuoteStatus.SENT)
    assert (await cancel.execute(sent, "Cambió la fecha")).status is QuoteStatus.CANCELLED
    with pytest.raises(InvalidQuoteStateError):
        await cancel.execute(sent)
    verifying = store.seed_quote(QuoteStatus.PAYMENT_STARTED, payment_in_verification=True)
    with pytest.raises(InvalidQuoteStateError):
        await cancel.execute(verifying)
    with pytest.raises(QuoteNotFoundError):
        await cancel.execute(uuid4())


async def test_list_filters_and_paginates_most_recent_first() -> None:
    store = FakeQuoteStore()
    first = store.seed_quote(QuoteStatus.SENT, sent_at=NOW - timedelta(hours=2))
    second = store.seed_quote(QuoteStatus.CANCELLED, sent_at=NOW - timedelta(hours=1))
    fake = FakeListQuotes(store, clock=_FrozenClock())
    page = await fake.execute(ListQuotesFilter(page=1, page_size=1))
    assert [item.quote_id for item in page.items] == [second]
    assert page.total == 2
    only_sent = await fake.execute(ListQuotesFilter(status=QuoteStatus.SENT))
    assert [item.quote_id for item in only_sent.items] == [first]


async def test_find_clients_by_name_fragment_and_exact_phone() -> None:
    store = FakeQuoteStore()
    carlos = store.add_client("+51999888777", "Carlos Rodríguez")
    store.add_client("+51955111222", "María Pérez")
    fake = FakeFindClients(store, clock=_FrozenClock())
    by_name = await fake.execute(FindClientsFilter(q="carl"))
    assert [client.id for client in by_name.items] == [carlos.id]
    by_phone = await fake.execute(FindClientsFilter(phone="999 888 777"))
    assert [client.id for client in by_phone.items] == [carlos.id]
    assert by_phone.total == 1


async def test_existing_phone_reuses_the_client_without_overwriting_the_name() -> None:
    store = FakeQuoteStore()
    create = FakeCreateQuote(store, clock=_FrozenClock())
    first = await create.execute(_create_input())
    second = await create.execute(
        _create_input(client=ClientInput(phone="999888777", full_name="Otro Nombre"))
    )
    assert second.client_id == first.client_id
    assert second.quote_id != first.quote_id
    assert store.get_client(first.client_id).full_name == "Carlos Rodríguez"


def test_fakes_take_no_session_and_no_messaging_dependency() -> None:
    forbidden = ("AsyncSession", "IMessagingPort", "EnqueueMessage", "Session")
    for fake in (
        FakeCreateQuote,
        FakeGetQuote,
        FakeListQuotes,
        FakePayAdvance,
        FakeCancelQuote,
        FakeExpireDueQuotes,
        FakeFindClients,
        FakeGetClient,
        FakeQuoteStore,
    ):
        for name, parameter in inspect.signature(fake).parameters.items():
            annotation = getattr(parameter.annotation, "__name__", str(parameter.annotation))
            assert not any(word in annotation for word in forbidden), (fake.__name__, name)
            assert not any(word.lower() in name for word in ("session", "messaging")), name


def test_each_fake_satisfies_its_port() -> None:
    store = FakeQuoteStore()
    create: ICreateQuotePort = FakeCreateQuote(store)
    get: IGetQuotePort = FakeGetQuote(store)
    listing: IListQuotesPort = FakeListQuotes(store)
    pay: IPayAdvancePort = FakePayAdvance(store)
    cancel: ICancelQuotePort = FakeCancelQuote(store)
    expire: IExpireDueQuotesPort = FakeExpireDueQuotes(store)
    find: IFindClientsPort = FakeFindClients(store)
    client: IGetClientPort = FakeGetClient(store)
    for fake in (create, get, listing, pay, cancel, expire, find, client):
        assert inspect.iscoroutinefunction(fake.execute)
