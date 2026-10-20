"""Casos de uso de cotización y clientes falsos, deterministas y con escenarios (spec 08).

Permiten al bot y al frontend avanzar sin las implementaciones reales y definen "terminado":
la suite ``tests/application/quote_ports_contract.py`` pasa contra estos fakes y deberá pasar
contra cada implementación real. Comparten un ``FakeQuoteStore`` en memoria para que
``CreateQuote`` seguido de ``GetQuote``, ``PayAdvance`` o ``GetClient`` sea coherente.

Siguen la regla de transacción del contrato: no reciben sesión, no confirman y no envían
mensajes. Los identificadores salen de ``uuid5`` sobre un contador, no de ``uuid4``.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import ClassVar
from uuid import NAMESPACE_URL, UUID, uuid5

from app.application.dtos.availability_dto import AvailabilityStatus
from app.application.dtos.client_dto import (
    ClientDetailDTO,
    ClientDTO,
    ClientQuoteSummaryDTO,
    FindClientsFilter,
)
from app.application.dtos.page_dto import PageDTO
from app.application.dtos.quote_dto import (
    BankTransferInstructionDTO,
    CancelledQuoteDTO,
    ClientSummaryDTO,
    CreatedQuoteDTO,
    CreateQuoteInput,
    ListQuotesFilter,
    PayAdvanceResultDTO,
    PaymentInstructionsDTO,
    QuoteBreakdownDTO,
    QuoteDetailDTO,
    QuoteExtraDetailDTO,
    QuoteExtraInput,
    QuoteListItemDTO,
    QuotePackageDTO,
    QuotePaymentDTO,
    QuoteThemeDTO,
    WalletInstructionDTO,
)
from app.application.ports.input.client_read_port import IFindClientsPort, IGetClientPort
from app.application.ports.input.quote_create_port import ICreateQuotePort
from app.application.ports.input.quote_expiry_port import IExpireDueQuotesPort
from app.application.ports.input.quote_lifecycle_port import ICancelQuotePort, IPayAdvancePort
from app.application.ports.input.quote_read_port import IGetQuotePort, IListQuotesPort
from app.application.ports.output.clock_port import IClockPort
from app.domain.entities.payment import PaymentConcept, PaymentValidationStatus
from app.domain.entities.quote import QuoteSource, QuoteStatus
from app.domain.exceptions.quote_exceptions import (
    AvailabilityAlternative,
    AvailabilityConflictError,
    AvailabilityRejectedError,
    ClientNotFoundError,
    InvalidQuoteStateError,
    QuoteExpiredError,
    QuoteNotFoundError,
    SimultaneousThresholdExceededError,
)
from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.phone_number import PhoneNumber

QUOTE_VALIDITY = timedelta(hours=24)
# Equivale a ``AVAILABILITY_RECHECK_MINUTES`` (60 por defecto) en la implementación real.
AVAILABILITY_RECHECK_WINDOW = timedelta(minutes=60)
_OPEN_STATUSES = frozenset({QuoteStatus.SENT, QuoteStatus.PAYMENT_STARTED})

# Vector de importes del ejemplo de ``POST /quotes`` (los fakes no recalculan precios).
SERVICES_SUBTOTAL = Decimal("1000.00")
MOBILITY_AMOUNT = Decimal("80.50")
ADVANCE_AMOUNT = Decimal("100.00")
CALCULATED_DISTANCE_KM = Decimal("18.40")
CALCULATED_TRANSIT_MINUTES = 55
_PACKAGE_NAME = "Hora Loca Medium"
_PACKAGE_BASE_PRICE = Decimal("750.00")
_THEME_NAME = "Selva"
_EXTRA_NAME = "Extra de prueba"
_EXTRA_UNIT_PRICE = Decimal("250.00")
_ALTERNATIVES = (AvailabilityAlternative(date(2026, 10, 15), time(18, 0)),)
_PAYMENT_INSTRUCTIONS = PaymentInstructionsDTO(
    yape=WalletInstructionDTO(phone="+51900111222", holder="EventPro SAC"),
    plin=WalletInstructionDTO(phone="+51900111222", holder="EventPro SAC"),
    bank_transfer=BankTransferInstructionDTO(
        bank="BCP",
        account="194-1234567-0-12",
        cci="00219400123456701234",
        holder="EventPro SAC",
    ),
)


class FakeScenario(StrEnum):
    """Efecto que un fake simula; ``OK`` es el camino feliz con estado en memoria."""

    OK = "OK"
    AVAILABILITY_CONFLICT = "AVAILABILITY_CONFLICT"
    SIMULTANEOUS_THRESHOLD = "SIMULTANEOUS_THRESHOLD"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    QUOTE_NOT_FOUND = "QUOTE_NOT_FOUND"
    QUOTE_EXPIRED = "QUOTE_EXPIRED"
    INVALID_QUOTE_STATE = "INVALID_QUOTE_STATE"
    PAYMENT_IN_VERIFICATION = "PAYMENT_IN_VERIFICATION"
    CLIENT_NOT_FOUND = "CLIENT_NOT_FOUND"


DEFAULT_NOW = datetime(2026, 10, 7, 15, 0, tzinfo=UTC)


class _FixedClock:
    """Reloj por defecto de los fakes: un instante fijo, como en las pruebas de mensajería."""

    def utcnow(self) -> datetime:
        return DEFAULT_NOW


@dataclass
class StoredClient:
    id: UUID
    phone: str
    full_name: str
    dni: str | None
    ruc: str | None
    created_at: datetime


@dataclass
class StoredQuote:
    id: UUID
    client_id: UUID
    source: QuoteSource
    event_date: date
    event_time: time
    location_address: str
    location_district: str
    package_id: UUID
    theme_id: UUID | None
    extras: tuple[QuoteExtraInput, ...]
    services_subtotal: Decimal
    calculated_distance_km: Decimal | None
    calculated_transit_minutes: int | None
    final_mobility_amount: Decimal
    advance_amount: Decimal
    status: QuoteStatus
    sent_at: datetime
    expires_at: datetime
    observations: str | None = None
    payment_in_verification: bool = False
    cancel_reason: str | None = None
    payments: list[QuotePaymentDTO] = field(default_factory=list)

    @property
    def total_amount(self) -> Decimal:
        return self.services_subtotal + self.final_mobility_amount

    @property
    def pending_balance(self) -> Decimal:
        return self.total_amount - self.advance_amount


class FakeQuoteStore:
    """Cotizaciones y clientes en memoria, compartidos por los ocho fakes."""

    def __init__(self) -> None:
        self._clients: dict[UUID, StoredClient] = {}
        self._quotes: dict[UUID, StoredQuote] = {}
        self._sequence = {"client": 0, "quote": 0, "payment": 0}

    def next_id(self, kind: str) -> UUID:
        self._sequence[kind] += 1
        return uuid5(NAMESPACE_URL, f"eventpro:fake-{kind}:{self._sequence[kind]}")

    def add_client(
        self,
        phone: str,
        full_name: str,
        dni: str | None = None,
        ruc: str | None = None,
        created_at: datetime = DEFAULT_NOW,
    ) -> StoredClient:
        client = StoredClient(
            self.next_id("client"), PhoneNumber.parse(phone).value, full_name, dni, ruc, created_at
        )
        self._clients[client.id] = client
        return client

    def find_client_by_phone(self, phone: str) -> StoredClient | None:
        normalized = PhoneNumber.parse(phone).value
        return next((c for c in self._clients.values() if c.phone == normalized), None)

    def get_client(self, client_id: UUID) -> StoredClient:
        try:
            return self._clients[client_id]
        except KeyError:
            raise ClientNotFoundError("El cliente solicitado no existe.") from None

    def clients(self) -> list[StoredClient]:
        return list(self._clients.values())

    def add_quote(self, quote: StoredQuote) -> StoredQuote:
        self._quotes[quote.id] = quote
        return quote

    def get_quote(self, quote_id: UUID) -> StoredQuote:
        try:
            return self._quotes[quote_id]
        except KeyError:
            raise QuoteNotFoundError("La cotización solicitada no existe.") from None

    def quotes(self) -> list[StoredQuote]:
        return list(self._quotes.values())

    def seed_quote(
        self,
        status: QuoteStatus = QuoteStatus.SENT,
        *,
        payment_in_verification: bool = False,
        client_id: UUID | None = None,
        sent_at: datetime = DEFAULT_NOW,
        event_date: date = date(2026, 10, 15),
    ) -> UUID:
        """Deja una cotización en el estado pedido y devuelve su identificador."""

        if client_id is None:
            number = len(self._clients) + 1
            client_id = self.add_client(f"+519{number:08d}", f"Cliente de prueba {number}").id
        quote = self.add_quote(
            build_stored_quote(
                self,
                client_id=client_id,
                sent_at=sent_at,
                event_date=event_date,
                status=status,
            )
        )
        if payment_in_verification:
            quote.payment_in_verification = True
            quote.payments.append(
                QuotePaymentDTO(
                    self.next_id("payment"),
                    PaymentConcept.ADVANCE,
                    PaymentValidationStatus.PENDING_VERIFICATION,
                )
            )
        return quote.id


def build_stored_quote(
    store: FakeQuoteStore,
    *,
    client_id: UUID,
    sent_at: datetime,
    event_date: date = date(2026, 10, 15),
    event_time: time = time(21, 30),
    status: QuoteStatus = QuoteStatus.SENT,
    dto: CreateQuoteInput | None = None,
) -> StoredQuote:
    exempt = dto is not None and dto.client_provides_mobility
    return StoredQuote(
        id=store.next_id("quote"),
        client_id=client_id,
        source=dto.source if dto else QuoteSource.WHATSAPP,
        event_date=dto.event_date if dto else event_date,
        event_time=dto.event_time if dto else event_time,
        location_address=dto.location_address if dto else "Av. Benavides 2150",
        location_district=dto.location_district if dto else "Miraflores",
        package_id=dto.package_id if dto else uuid5(NAMESPACE_URL, "eventpro:fake-package"),
        theme_id=dto.theme_id if dto else None,
        extras=dto.extras if dto else (),
        services_subtotal=SERVICES_SUBTOTAL,
        calculated_distance_km=None if exempt else CALCULATED_DISTANCE_KM,
        calculated_transit_minutes=None if exempt else CALCULATED_TRANSIT_MINUTES,
        final_mobility_amount=Decimal("0.00") if exempt else MOBILITY_AMOUNT,
        advance_amount=ADVANCE_AMOUNT,
        status=status,
        sent_at=sent_at,
        expires_at=sent_at + QUOTE_VALIDITY,
        observations=dto.observations if dto else None,
    )


def _availability_error(scenario: FakeScenario) -> AvailabilityRejectedError:
    if scenario is FakeScenario.AVAILABILITY_CONFLICT:
        return AvailabilityConflictError(
            "El cupo ya no está disponible. Puede elegir otra fecha u horario "
            "o solicitar la ayuda de un encargado.",
            alternatives=_ALTERNATIVES,
            handoff_available=True,
        )
    return SimultaneousThresholdExceededError(
        "Se superaría el máximo de shows simultáneos. Puede elegir otra fecha u horario "
        "o solicitar la ayuda de un encargado.",
        alternatives=_ALTERNATIVES,
        handoff_available=True,
    )


def _paginate[T](items: Sequence[T], page: int, page_size: int) -> PageDTO[T]:
    start = (page - 1) * page_size
    return PageDTO(
        items=tuple(items[start : start + page_size]),
        page=page,
        page_size=page_size,
        total=len(items),
    )


def _client_summary(client: StoredClient) -> ClientSummaryDTO:
    return ClientSummaryDTO(id=client.id, full_name=client.full_name, phone=client.phone)


class _ScenarioFake:
    """Base común: almacén, reloj y escenario validado contra los aplicables al puerto."""

    _EXTRA_SCENARIOS: ClassVar[frozenset[FakeScenario]] = frozenset()

    def __init__(self, store: FakeQuoteStore, *, clock: IClockPort | None = None) -> None:
        self._store = store
        self._clock: IClockPort = clock or _FixedClock()
        self._scenario = FakeScenario.OK

    @property
    def scenario(self) -> FakeScenario:
        return self._scenario

    @scenario.setter
    def scenario(self, value: FakeScenario) -> None:
        if value is not FakeScenario.OK and value not in self._EXTRA_SCENARIOS:
            raise ValueError(f"El escenario {value.value} no aplica a {type(self).__name__}.")
        self._scenario = value

    def _raise_availability_if_requested(self) -> None:
        if self._scenario in (
            FakeScenario.AVAILABILITY_CONFLICT,
            FakeScenario.SIMULTANEOUS_THRESHOLD,
        ):
            raise _availability_error(self._scenario)


_S = FakeScenario


class FakeCreateQuote(_ScenarioFake, ICreateQuotePort):
    _EXTRA_SCENARIOS = frozenset(
        {
            _S.AVAILABILITY_CONFLICT,
            _S.SIMULTANEOUS_THRESHOLD,
            _S.VALIDATION_ERROR,
            _S.CLIENT_NOT_FOUND,
        }
    )

    async def execute(self, dto: CreateQuoteInput) -> CreatedQuoteDTO:
        self._raise_availability_if_requested()
        if self._scenario is _S.VALIDATION_ERROR:
            raise ValidationError("La solicitud de cotización no cumple las reglas de negocio.")
        if self._scenario is _S.CLIENT_NOT_FOUND:
            if dto.client_id is None:
                raise ValueError("El escenario CLIENT_NOT_FOUND requiere un client_id.")
            raise ClientNotFoundError("El cliente solicitado no existe.")
        client_id = self._resolve_client(dto)
        quote = self._store.add_quote(
            build_stored_quote(
                self._store, client_id=client_id, sent_at=self._clock.utcnow(), dto=dto
            )
        )
        return CreatedQuoteDTO(
            quote_id=quote.id,
            client_id=client_id,
            source=quote.source,
            availability=AvailabilityStatus.AVAILABLE,
            services_subtotal=quote.services_subtotal,
            calculated_distance_km=quote.calculated_distance_km,
            calculated_transit_minutes=quote.calculated_transit_minutes,
            final_mobility_amount=quote.final_mobility_amount,
            total_amount=quote.total_amount,
            advance_amount=quote.advance_amount,
            pending_balance=quote.pending_balance,
            breakdown=QuoteBreakdownDTO(
                services_balance_due=quote.services_subtotal - quote.advance_amount,
                mobility_due=quote.final_mobility_amount,
            ),
            status=quote.status,
            sent_at=quote.sent_at,
            expires_at=quote.expires_at,
        )

    def _resolve_client(self, dto: CreateQuoteInput) -> UUID:
        if dto.client_id is not None:
            return self._store.get_client(dto.client_id).id
        assert dto.client is not None  # garantizado por CreateQuoteInput
        existing = self._store.find_client_by_phone(dto.client.phone)
        if existing is not None:
            return existing.id
        return self._store.add_client(
            dto.client.phone,
            dto.client.full_name,
            dto.client.dni,
            dto.client.ruc,
            self._clock.utcnow(),
        ).id


class FakeGetQuote(_ScenarioFake, IGetQuotePort):
    _EXTRA_SCENARIOS = frozenset({_S.QUOTE_NOT_FOUND})

    async def execute(self, quote_id: UUID) -> QuoteDetailDTO:
        if self._scenario is _S.QUOTE_NOT_FOUND:
            raise QuoteNotFoundError("La cotización solicitada no existe.")
        quote = self._store.get_quote(quote_id)
        client = self._store.get_client(quote.client_id)
        return QuoteDetailDTO(
            quote_id=quote.id,
            client=_client_summary(client),
            source=quote.source,
            event_date=quote.event_date,
            event_time=quote.event_time,
            location_address=quote.location_address,
            location_district=quote.location_district,
            package=QuotePackageDTO(quote.package_id, _PACKAGE_NAME, _PACKAGE_BASE_PRICE),
            theme=QuoteThemeDTO(quote.theme_id, _THEME_NAME) if quote.theme_id else None,
            extras=tuple(
                QuoteExtraDetailDTO(
                    extra_id=extra.extra_id,
                    name=_EXTRA_NAME,
                    quantity=extra.quantity,
                    unit_price=_EXTRA_UNIT_PRICE,
                    subtotal=_EXTRA_UNIT_PRICE * extra.quantity,
                )
                for extra in quote.extras
            ),
            services_subtotal=quote.services_subtotal,
            final_mobility_amount=quote.final_mobility_amount,
            mobility_overridden=False,
            total_amount=quote.total_amount,
            advance_amount=quote.advance_amount,
            pending_balance=quote.pending_balance,
            status=quote.status,
            sent_at=quote.sent_at,
            expires_at=quote.expires_at,
            observations=quote.observations,
            payments=tuple(quote.payments),
            event_id=None,
        )


class FakeListQuotes(_ScenarioFake, IListQuotesPort):
    _EXTRA_SCENARIOS = frozenset({_S.VALIDATION_ERROR})

    async def execute(self, filters: ListQuotesFilter) -> PageDTO[QuoteListItemDTO]:
        if self._scenario is _S.VALIDATION_ERROR:
            raise ValidationError("Los filtros de cotizaciones no son válidos.")
        matching = [
            quote
            for quote in self._store.quotes()
            if (filters.status is None or quote.status is filters.status)
            and (filters.client_id is None or quote.client_id == filters.client_id)
            and (filters.from_date is None or quote.event_date >= filters.from_date)
            and (filters.to_date is None or quote.event_date <= filters.to_date)
        ]
        # La más reciente primero; a igual instante, la creada después.
        ordered = sorted(
            enumerate(matching), key=lambda pair: (pair[1].sent_at, pair[0]), reverse=True
        )
        items = [
            QuoteListItemDTO(
                quote_id=quote.id,
                client=_client_summary(self._store.get_client(quote.client_id)),
                event_date=quote.event_date,
                package_name=_PACKAGE_NAME,
                total_amount=quote.total_amount,
                status=quote.status,
                expires_at=quote.expires_at,
            )
            for _, quote in ordered
        ]
        return _paginate(items, filters.page, filters.page_size)


class FakePayAdvance(_ScenarioFake, IPayAdvancePort):
    _EXTRA_SCENARIOS = frozenset(
        {
            _S.AVAILABILITY_CONFLICT,
            _S.SIMULTANEOUS_THRESHOLD,
            _S.QUOTE_NOT_FOUND,
            _S.QUOTE_EXPIRED,
            _S.INVALID_QUOTE_STATE,
        }
    )

    def __init__(self, store: FakeQuoteStore, *, clock: IClockPort | None = None) -> None:
        super().__init__(store, clock=clock)
        # ``None`` deriva el indicador de la antigüedad de la cotización; un valor lo fuerza.
        self.rechecked: bool | None = None

    async def execute(self, quote_id: UUID) -> PayAdvanceResultDTO:
        if self._scenario is _S.QUOTE_NOT_FOUND:
            raise QuoteNotFoundError("La cotización solicitada no existe.")
        if self._scenario is _S.QUOTE_EXPIRED:
            raise QuoteExpiredError("La cotización venció.")
        if self._scenario is _S.INVALID_QUOTE_STATE:
            raise InvalidQuoteStateError("La cotización no admite iniciar el pago.")
        self._raise_availability_if_requested()
        quote = self._store.get_quote(quote_id)
        if quote.status is QuoteStatus.EXPIRED:
            raise QuoteExpiredError("La cotización venció.")
        if quote.status not in _OPEN_STATUSES:
            raise InvalidQuoteStateError(f"La cotización está {quote.status.value}.")
        quote.status = QuoteStatus.PAYMENT_STARTED
        return PayAdvanceResultDTO(
            quote_id=quote.id,
            status=quote.status,
            availability=AvailabilityStatus.AVAILABLE,
            rechecked=(
                self.rechecked
                if self.rechecked is not None
                else self._clock.utcnow() - quote.sent_at > AVAILABILITY_RECHECK_WINDOW
            ),
            advance_amount=quote.advance_amount,
            payment_deadline=quote.expires_at,
            payment_instructions=_PAYMENT_INSTRUCTIONS,
        )


class FakeCancelQuote(_ScenarioFake, ICancelQuotePort):
    _EXTRA_SCENARIOS = frozenset(
        {_S.QUOTE_NOT_FOUND, _S.INVALID_QUOTE_STATE, _S.PAYMENT_IN_VERIFICATION}
    )

    async def execute(self, quote_id: UUID, reason: str | None = None) -> CancelledQuoteDTO:
        if self._scenario is _S.QUOTE_NOT_FOUND:
            raise QuoteNotFoundError("La cotización solicitada no existe.")
        if self._scenario is _S.INVALID_QUOTE_STATE:
            raise InvalidQuoteStateError("La cotización no se puede cancelar.")
        if self._scenario is _S.PAYMENT_IN_VERIFICATION:
            raise InvalidQuoteStateError("Hay un pago en verificación: resuélvalo primero.")
        quote = self._store.get_quote(quote_id)
        if quote.status not in _OPEN_STATUSES:
            raise InvalidQuoteStateError(f"La cotización está {quote.status.value}.")
        if quote.payment_in_verification:
            raise InvalidQuoteStateError("Hay un pago en verificación: resuélvalo primero.")
        quote.status = QuoteStatus.CANCELLED
        quote.cancel_reason = reason
        return CancelledQuoteDTO(quote_id=quote.id, status=quote.status)


class FakeExpireDueQuotes(_ScenarioFake, IExpireDueQuotesPort):
    """Vence las cotizaciones del almacén cuyo plazo ya pasó.

    ``due_count`` suma cotizaciones adicionales "vencidas" fuera del almacén; se consume en
    la primera ejecución (la segunda devuelve 0, es idempotente).
    """

    _EXTRA_SCENARIOS = frozenset({_S.PAYMENT_IN_VERIFICATION})

    def __init__(self, store: FakeQuoteStore, *, clock: IClockPort | None = None) -> None:
        super().__init__(store, clock=clock)
        self.due_count = 0

    async def execute(self) -> int:
        if self._scenario is _S.PAYMENT_IN_VERIFICATION:
            return 0
        now = self._clock.utcnow()
        expired = 0
        for quote in self._store.quotes():
            if (
                quote.status in _OPEN_STATUSES
                and quote.expires_at <= now
                and not quote.payment_in_verification
            ):
                quote.status = QuoteStatus.EXPIRED
                expired += 1
        total = expired + self.due_count
        self.due_count = 0
        return total


class FakeFindClients(_ScenarioFake, IFindClientsPort):
    async def execute(self, filters: FindClientsFilter) -> PageDTO[ClientDTO]:
        exact = PhoneNumber.parse(filters.phone).value if filters.phone else None
        needle = (filters.q or "").strip().lower()
        digits = "".join(ch for ch in needle if ch.isdigit())
        matching = [
            client
            for client in self._store.clients()
            if (exact is None or client.phone == exact)
            and (
                not needle
                or needle in client.full_name.lower()
                or (digits != "" and digits in client.phone)
            )
        ]
        items = [
            ClientDTO(
                id=client.id,
                phone=client.phone,
                full_name=client.full_name,
                dni=client.dni,
                ruc=client.ruc,
                created_at=client.created_at,
            )
            for client in matching
        ]
        return _paginate(items, filters.page, filters.page_size)


class FakeGetClient(_ScenarioFake, IGetClientPort):
    _EXTRA_SCENARIOS = frozenset({_S.CLIENT_NOT_FOUND})

    async def execute(self, client_id: UUID) -> ClientDetailDTO:
        if self._scenario is _S.CLIENT_NOT_FOUND:
            raise ClientNotFoundError("El cliente solicitado no existe.")
        client = self._store.get_client(client_id)
        quotes = sorted(
            (q for q in self._store.quotes() if q.client_id == client.id),
            key=lambda quote: quote.event_date,
            reverse=True,
        )
        return ClientDetailDTO(
            id=client.id,
            phone=client.phone,
            full_name=client.full_name,
            dni=client.dni,
            ruc=client.ruc,
            created_at=client.created_at,
            quotes=tuple(
                ClientQuoteSummaryDTO(
                    quote_id=quote.id,
                    event_date=quote.event_date,
                    total_amount=quote.total_amount,
                    status=quote.status,
                )
                for quote in quotes
            ),
        )
