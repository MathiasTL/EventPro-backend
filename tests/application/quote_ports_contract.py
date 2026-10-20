"""Suite de contrato de los puertos de entrada de cotización y clientes (spec 08, sección 2.6).

La ejecutan los fakes hoy y deberá pasarla cada implementación real: una subclase concreta
(``Test...``) implementa los ganchos. Estas clases no empiezan por ``Test``, así que pytest no
las recolecta; funcionan igual que ``MessagingPortContract``.

Ganchos (todos abstractos):

* ``make_port()``: devuelve el puerto bajo prueba.
* ``seed_quote(status, ...)``: deja una cotización en el estado pedido y devuelve su ``id``.
  ``age`` es cuánto tiempo atrás se envió; ``client_id`` y ``event_date`` fijan su cliente y su
  fecha de evento.
* ``seed_client(phone, full_name)``: deja un cliente y devuelve su ``id``.
* ``arrange(port, scenario)``: configura el escenario de error (o ``OK`` para volver al normal).
* ``quote_count()``: cuántas cotizaciones existen, para comprobar que un error no crea ninguna.
* ``assert_nothing_committed()``: tras ejecutar un caso de uso sin que el llamador confirme,
  otra sesión no ve cambios. El fake lo cumple por construcción.
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.application.dtos.client_dto import FindClientsFilter
from app.application.dtos.quote_dto import (
    ClientInput,
    CreatedQuoteDTO,
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
    FakeScenario,
)

PACKAGE_ID = UUID("00000000-0000-0000-0000-0000000000a1")
PHONE = "+51999888777"
SENT_OVERDUE = timedelta(hours=25)
RECHECK_WINDOW_EXCEEDED = timedelta(minutes=90)


def create_input(**overrides: Any) -> CreateQuoteInput:
    values: dict[str, Any] = {
        "package_id": PACKAGE_ID,
        "event_date": date(2026, 10, 15),
        "event_time": time(21, 30),
        "location_address": "Av. Benavides 2150",
        "location_district": "Miraflores",
        "client": ClientInput(phone=PHONE, full_name="Carlos Rodríguez"),
    }
    values.update(overrides)
    return CreateQuoteInput(**values)


class _Hooks:
    def make_port(self) -> Any:
        raise NotImplementedError

    def seed_quote(
        self,
        status: QuoteStatus,
        *,
        payment_in_verification: bool = False,
        age: timedelta = timedelta(0),
        client_id: UUID | None = None,
        event_date: date | None = None,
    ) -> UUID:
        raise NotImplementedError

    def seed_client(self, phone: str, full_name: str) -> UUID:
        raise NotImplementedError

    def arrange(self, port: Any, scenario: FakeScenario) -> None:
        raise NotImplementedError

    def quote_count(self) -> int:
        raise NotImplementedError

    def assert_nothing_committed(self) -> None:
        raise NotImplementedError


def _assert_aware_utc(value: object) -> None:
    assert isinstance(value, datetime)
    assert value.tzinfo is not None
    assert value.utcoffset() == timedelta(0)


class CreateQuoteContract(_Hooks):
    @pytest.fixture
    def port(self) -> ICreateQuotePort:
        port: ICreateQuotePort = self.make_port()
        return port

    async def test_creates_a_sent_quote_expiring_in_24_hours(self, port: ICreateQuotePort) -> None:
        created = await port.execute(create_input())
        assert created.status is QuoteStatus.SENT
        assert created.expires_at - created.sent_at == timedelta(hours=24)

    async def test_created_quote_dates_are_utc_aware(self, port: ICreateQuotePort) -> None:
        created = await port.execute(create_input())
        _assert_aware_utc(created.sent_at)
        _assert_aware_utc(created.expires_at)

    async def test_expires_at_is_sent_at_plus_24_hours(self, port: ICreateQuotePort) -> None:
        created = await port.execute(create_input())
        assert created.expires_at == created.sent_at + timedelta(hours=24)

    async def test_totals_are_consistent(self, port: ICreateQuotePort) -> None:
        created = await port.execute(create_input())
        assert created.total_amount == created.services_subtotal + created.final_mobility_amount
        assert created.pending_balance == created.total_amount - created.advance_amount
        assert created.breakdown.mobility_due == created.final_mobility_amount

    async def test_existing_phone_reuses_the_client(self, port: ICreateQuotePort) -> None:
        first = await port.execute(create_input())
        second = await port.execute(
            create_input(client=ClientInput(phone="999 888 777", full_name="Otro Nombre"))
        )
        assert second.client_id == first.client_id

    async def test_client_and_client_id_together_or_neither_is_a_validation_error(
        self, port: ICreateQuotePort
    ) -> None:
        with pytest.raises(ValidationError):
            create_input(client_id=uuid4())
        with pytest.raises(ValidationError):
            create_input(client=None)

    async def test_exempt_mobility_charges_zero(self, port: ICreateQuotePort) -> None:
        created = await port.execute(create_input(client_provides_mobility=True))
        assert created.final_mobility_amount == Decimal("0.00")
        assert created.total_amount == created.services_subtotal

    async def _assert_rejection(
        self,
        port: ICreateQuotePort,
        scenario: FakeScenario,
        error_type: type[AvailabilityRejectedError],
    ) -> None:
        self.arrange(port, scenario)
        with pytest.raises(error_type) as caught:
            await port.execute(create_input())
        assert type(caught.value) is error_type
        assert len(caught.value.alternatives) >= 1
        assert caught.value.handoff_available is True

    async def test_availability_conflict_carries_alternatives_and_handoff(
        self, port: ICreateQuotePort
    ) -> None:
        await self._assert_rejection(
            port, FakeScenario.AVAILABILITY_CONFLICT, AvailabilityConflictError
        )

    async def test_simultaneous_threshold_carries_alternatives_and_handoff(
        self, port: ICreateQuotePort
    ) -> None:
        await self._assert_rejection(
            port, FakeScenario.SIMULTANEOUS_THRESHOLD, SimultaneousThresholdExceededError
        )

    async def test_error_creates_no_quote(self, port: ICreateQuotePort) -> None:
        before = self.quote_count()
        self.arrange(port, FakeScenario.AVAILABILITY_CONFLICT)
        with pytest.raises(AvailabilityConflictError):
            await port.execute(create_input())
        assert self.quote_count() == before

    async def test_unknown_client_id_raises_client_not_found(self, port: ICreateQuotePort) -> None:
        with pytest.raises(ClientNotFoundError):
            await port.execute(create_input(client=None, client_id=uuid4()))

    async def test_create_twice_creates_two_distinct_quotes(self, port: ICreateQuotePort) -> None:
        first: CreatedQuoteDTO = await port.execute(create_input())
        second: CreatedQuoteDTO = await port.execute(create_input())
        assert first.quote_id != second.quote_id
        assert self.quote_count() == 2

    async def test_does_not_commit(self, port: ICreateQuotePort) -> None:
        await port.execute(create_input())
        self.assert_nothing_committed()


class GetQuoteContract(_Hooks):
    @pytest.fixture
    def port(self) -> IGetQuotePort:
        port: IGetQuotePort = self.make_port()
        return port

    async def test_returns_the_created_quote_detail(self, port: IGetQuotePort) -> None:
        quote_id = self.seed_quote(QuoteStatus.SENT)
        detail = await port.execute(quote_id)
        assert detail.quote_id == quote_id
        assert detail.status is QuoteStatus.SENT
        assert detail.total_amount == detail.services_subtotal + detail.final_mobility_amount
        assert detail.pending_balance == detail.total_amount - detail.advance_amount

    async def test_unknown_quote_raises_quote_not_found(self, port: IGetQuotePort) -> None:
        with pytest.raises(QuoteNotFoundError):
            await port.execute(uuid4())


class ListQuotesContract(_Hooks):
    @pytest.fixture
    def port(self) -> IListQuotesPort:
        port: IListQuotesPort = self.make_port()
        return port

    async def test_filters_by_status(self, port: IListQuotesPort) -> None:
        sent = self.seed_quote(QuoteStatus.SENT)
        cancelled = self.seed_quote(QuoteStatus.CANCELLED)
        page = await port.execute(ListQuotesFilter(status=QuoteStatus.CANCELLED))
        ids = {item.quote_id for item in page.items}
        assert cancelled in ids
        assert sent not in ids
        assert {item.status for item in page.items} == {QuoteStatus.CANCELLED}

    async def test_filters_by_client_id(self, port: IListQuotesPort) -> None:
        client_id = self.seed_client("+51955111222", "María Pérez")
        mine = self.seed_quote(QuoteStatus.SENT, client_id=client_id)
        other = self.seed_quote(QuoteStatus.SENT)
        page = await port.execute(ListQuotesFilter(client_id=client_id))
        ids = {item.quote_id for item in page.items}
        assert ids == {mine}
        assert other not in ids
        assert page.items[0].client.id == client_id

    async def test_filters_by_event_date_range(self, port: IListQuotesPort) -> None:
        early = self.seed_quote(QuoteStatus.SENT, event_date=date(2026, 10, 10))
        middle = self.seed_quote(QuoteStatus.SENT, event_date=date(2026, 10, 20))
        late = self.seed_quote(QuoteStatus.SENT, event_date=date(2026, 11, 5))
        page = await port.execute(
            ListQuotesFilter(from_date=date(2026, 10, 15), to_date=date(2026, 10, 31))
        )
        ids = {item.quote_id for item in page.items}
        assert middle in ids
        assert early not in ids
        assert late not in ids

    async def test_paginates_and_reports_total(self, port: IListQuotesPort) -> None:
        client_id = self.seed_client("+51955111222", "María Pérez")
        for _ in range(3):
            self.seed_quote(QuoteStatus.SENT, client_id=client_id)
        first = await port.execute(ListQuotesFilter(client_id=client_id, page=1, page_size=2))
        second = await port.execute(ListQuotesFilter(client_id=client_id, page=2, page_size=2))
        assert (first.total, first.page, first.page_size, len(first.items)) == (3, 1, 2, 2)
        assert (second.total, second.page, len(second.items)) == (3, 2, 1)
        assert not {i.quote_id for i in first.items} & {i.quote_id for i in second.items}

    async def test_inverted_range_is_a_validation_error(self, port: IListQuotesPort) -> None:
        with pytest.raises(ValidationError):
            ListQuotesFilter(from_date=date(2026, 10, 31), to_date=date(2026, 10, 1))


class PayAdvanceContract(_Hooks):
    @pytest.fixture
    def port(self) -> IPayAdvancePort:
        port: IPayAdvancePort = self.make_port()
        return port

    async def test_sent_moves_to_payment_started_with_instructions(
        self, port: IPayAdvancePort
    ) -> None:
        quote_id = self.seed_quote(QuoteStatus.SENT)
        result = await port.execute(quote_id)
        assert result.quote_id == quote_id
        assert result.status is QuoteStatus.PAYMENT_STARTED
        instructions = result.payment_instructions
        assert instructions.yape.phone
        assert instructions.plin.phone
        assert instructions.bank_transfer.account
        assert instructions.bank_transfer.cci
        _assert_aware_utc(result.payment_deadline)

    async def test_pay_advance_twice_is_idempotent(self, port: IPayAdvancePort) -> None:
        quote_id = self.seed_quote(QuoteStatus.SENT)
        first = await port.execute(quote_id)
        second = await port.execute(quote_id)
        assert second.status is QuoteStatus.PAYMENT_STARTED
        assert second.payment_deadline == first.payment_deadline
        assert second.advance_amount == first.advance_amount

    async def test_rechecked_only_after_the_recheck_window(self, port: IPayAdvancePort) -> None:
        fresh = await port.execute(self.seed_quote(QuoteStatus.SENT))
        aged = await port.execute(self.seed_quote(QuoteStatus.SENT, age=RECHECK_WINDOW_EXCEEDED))
        assert fresh.rechecked is False
        assert aged.rechecked is True

    async def _assert_no_payment_data_and_state_kept(
        self,
        port: IPayAdvancePort,
        scenario: FakeScenario,
        error_type: type[AvailabilityRejectedError],
    ) -> None:
        quote_id = self.seed_quote(QuoteStatus.SENT)
        self.arrange(port, scenario)
        with pytest.raises(error_type) as caught:
            await port.execute(quote_id)
        assert not hasattr(caught.value, "payment_instructions")
        assert caught.value.handoff_available is True
        assert len(caught.value.alternatives) >= 1
        # La cotización conserva su estado: sigue en SENT y puede pagarse cuando haya cupo.
        self.arrange(port, FakeScenario.OK)
        result = await port.execute(quote_id)
        assert result.status is QuoteStatus.PAYMENT_STARTED

    async def test_availability_conflict_hides_payment_data_and_keeps_state(
        self, port: IPayAdvancePort
    ) -> None:
        await self._assert_no_payment_data_and_state_kept(
            port, FakeScenario.AVAILABILITY_CONFLICT, AvailabilityConflictError
        )

    async def test_simultaneous_threshold_hides_payment_data(self, port: IPayAdvancePort) -> None:
        await self._assert_no_payment_data_and_state_kept(
            port, FakeScenario.SIMULTANEOUS_THRESHOLD, SimultaneousThresholdExceededError
        )

    async def test_expired_quote_raises_quote_expired(self, port: IPayAdvancePort) -> None:
        with pytest.raises(QuoteExpiredError):
            await port.execute(self.seed_quote(QuoteStatus.EXPIRED))

    async def test_converted_and_cancelled_raise_invalid_state(self, port: IPayAdvancePort) -> None:
        for status in (QuoteStatus.CONVERTED, QuoteStatus.CANCELLED):
            with pytest.raises(InvalidQuoteStateError):
                await port.execute(self.seed_quote(status))

    async def test_unknown_quote_raises_quote_not_found(self, port: IPayAdvancePort) -> None:
        with pytest.raises(QuoteNotFoundError):
            await port.execute(uuid4())

    async def test_does_not_commit(self, port: IPayAdvancePort) -> None:
        await port.execute(self.seed_quote(QuoteStatus.SENT))
        self.assert_nothing_committed()


class CancelQuoteContract(_Hooks):
    @pytest.fixture
    def port(self) -> ICancelQuotePort:
        port: ICancelQuotePort = self.make_port()
        return port

    async def test_cancels_from_sent(self, port: ICancelQuotePort) -> None:
        quote_id = self.seed_quote(QuoteStatus.SENT)
        result = await port.execute(quote_id)
        assert (result.quote_id, result.status) == (quote_id, QuoteStatus.CANCELLED)

    async def test_cancels_from_payment_started(self, port: ICancelQuotePort) -> None:
        result = await port.execute(self.seed_quote(QuoteStatus.PAYMENT_STARTED))
        assert result.status is QuoteStatus.CANCELLED

    async def test_cancels_with_and_without_reason(self, port: ICancelQuotePort) -> None:
        with_reason = await port.execute(self.seed_quote(QuoteStatus.SENT), "El cliente cambió")
        without_reason = await port.execute(self.seed_quote(QuoteStatus.SENT))
        assert with_reason.status is QuoteStatus.CANCELLED
        assert without_reason.status is QuoteStatus.CANCELLED

    async def test_payment_in_verification_raises_invalid_state(
        self, port: ICancelQuotePort
    ) -> None:
        quote_id = self.seed_quote(QuoteStatus.PAYMENT_STARTED, payment_in_verification=True)
        with pytest.raises(InvalidQuoteStateError):
            await port.execute(quote_id)

    async def test_cancel_an_already_cancelled_quote_raises_invalid_state(
        self, port: ICancelQuotePort
    ) -> None:
        quote_id = self.seed_quote(QuoteStatus.SENT)
        await port.execute(quote_id)
        with pytest.raises(InvalidQuoteStateError):
            await port.execute(quote_id)

    async def test_unknown_quote_raises_quote_not_found(self, port: ICancelQuotePort) -> None:
        with pytest.raises(QuoteNotFoundError):
            await port.execute(uuid4())

    async def test_does_not_commit(self, port: ICancelQuotePort) -> None:
        await port.execute(self.seed_quote(QuoteStatus.SENT))
        self.assert_nothing_committed()


class ExpireDueQuotesContract(_Hooks):
    @pytest.fixture
    def port(self) -> IExpireDueQuotesPort:
        port: IExpireDueQuotesPort = self.make_port()
        return port

    async def test_returns_the_count_of_expired_quotes(self, port: IExpireDueQuotesPort) -> None:
        self.seed_quote(QuoteStatus.SENT, age=SENT_OVERDUE)
        self.seed_quote(QuoteStatus.PAYMENT_STARTED, age=SENT_OVERDUE)
        assert await port.execute() == 2

    async def test_expire_twice_returns_zero_the_second_time(
        self, port: IExpireDueQuotesPort
    ) -> None:
        self.seed_quote(QuoteStatus.SENT, age=SENT_OVERDUE)
        assert await port.execute() == 1
        assert await port.execute() == 0

    async def test_live_quote_is_not_expired(self, port: IExpireDueQuotesPort) -> None:
        self.seed_quote(QuoteStatus.SENT)
        assert await port.execute() == 0

    async def test_quote_with_payment_in_verification_is_not_expired(
        self, port: IExpireDueQuotesPort
    ) -> None:
        self.seed_quote(QuoteStatus.PAYMENT_STARTED, age=SENT_OVERDUE, payment_in_verification=True)
        self.seed_quote(QuoteStatus.SENT, age=SENT_OVERDUE)
        assert await port.execute() == 1


class FindClientsContract(_Hooks):
    @pytest.fixture
    def port(self) -> IFindClientsPort:
        port: IFindClientsPort = self.make_port()
        return port

    async def test_finds_by_name_fragment(self, port: IFindClientsPort) -> None:
        carlos = self.seed_client(PHONE, "Carlos Rodríguez")
        self.seed_client("+51955111222", "María Pérez")
        page = await port.execute(FindClientsFilter(q="carl"))
        assert [client.id for client in page.items] == [carlos]
        assert page.total == 1

    async def test_finds_by_phone_in_any_accepted_format(self, port: IFindClientsPort) -> None:
        carlos = self.seed_client(PHONE, "Carlos Rodríguez")
        self.seed_client("+51955111222", "María Pérez")
        for raw in ("+51999888777", "51999888777", "999888777", "999 888 777"):
            page = await port.execute(FindClientsFilter(phone=raw))
            assert [client.id for client in page.items] == [carlos], raw

    async def test_paginates_and_reports_total(self, port: IFindClientsPort) -> None:
        for number in range(3):
            self.seed_client(f"+5195500000{number}", f"Cliente Número {number}")
        first = await port.execute(FindClientsFilter(q="Número", page=1, page_size=2))
        second = await port.execute(FindClientsFilter(q="Número", page=2, page_size=2))
        assert (first.total, len(first.items)) == (3, 2)
        assert (second.total, len(second.items)) == (3, 1)
        assert not {c.id for c in first.items} & {c.id for c in second.items}


class GetClientContract(_Hooks):
    @pytest.fixture
    def port(self) -> IGetClientPort:
        port: IGetClientPort = self.make_port()
        return port

    async def test_returns_the_client_with_its_quotes_summary(self, port: IGetClientPort) -> None:
        client_id = self.seed_client(PHONE, "Carlos Rodríguez")
        quote_id = self.seed_quote(QuoteStatus.SENT, client_id=client_id)
        self.seed_quote(QuoteStatus.SENT)
        detail = await port.execute(client_id)
        assert (detail.id, detail.phone, detail.full_name) == (client_id, PHONE, "Carlos Rodríguez")
        assert [quote.quote_id for quote in detail.quotes] == [quote_id]
        assert detail.quotes[0].status is QuoteStatus.SENT

    async def test_unknown_client_raises_client_not_found(self, port: IGetClientPort) -> None:
        with pytest.raises(ClientNotFoundError):
            await port.execute(uuid4())
