"""Agregado Quote: cotización con liquidación congelada y ciclo de vida (E1, RN-09)."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Self
from uuid import UUID, uuid4

from app.domain.exceptions.quote_exceptions import InvalidQuoteStateError, QuoteExpiredError
from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.liquidation import Liquidation
from app.domain.value_objects.mobility import MobilityResult, MobilityScenario
from app.domain.value_objects.money import Money


class QuoteStatus(StrEnum):
    SENT = "SENT"
    PAYMENT_STARTED = "PAYMENT_STARTED"
    CONVERTED = "CONVERTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class QuoteSource(StrEnum):
    WHATSAPP = "WHATSAPP"
    MANUAL = "MANUAL"


_OPEN_STATUSES = frozenset({QuoteStatus.SENT, QuoteStatus.PAYMENT_STARTED})


def _require_aware(value: datetime, name: str) -> datetime:
    """Exige un instante con zona horaria y lo normaliza a UTC."""

    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError(f"{name} debe incluir zona horaria")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class QuoteExtraLine:
    """Extra contratado en una cotización; ``subtotal`` = ``unit_price`` × ``quantity``."""

    extra_id: UUID
    quantity: int
    unit_price: Money
    subtotal: Money

    def __post_init__(self) -> None:
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int):
            raise ValidationError("quantity debe ser un entero")
        if self.quantity <= 0:
            raise ValidationError("La cantidad de un extra debe ser mayor que cero")
        if self.unit_price.amount < 0:
            raise ValidationError("El precio de un extra no puede ser negativo")
        if self.subtotal != self.unit_price * self.quantity:
            raise ValidationError("subtotal debe ser unit_price × quantity")


@dataclass(kw_only=True)
class Quote:
    client_id: UUID
    source: QuoteSource
    event_date: date
    event_time: time
    location_address: str
    location_district: str
    package_id: UUID
    liquidation: Liquidation
    sent_at: datetime
    expires_at: datetime
    theme_id: UUID | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    client_provides_mobility: bool = False
    calculated_distance_km: Decimal | None = None
    calculated_transit_minutes: int | None = None
    base_mobility_amount: Money = field(default_factory=Money.zero)
    mobility_overridden: bool = False
    mobility_override_reason: str | None = None
    extras: tuple[QuoteExtraLine, ...] = ()
    status: QuoteStatus = QuoteStatus.SENT
    manual_request_hash: str | None = None
    # Motivo de la cancelación: solo vive en memoria (no hay columna; lo audita el caso de uso).
    cancellation_reason: str | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        _require_aware(self.sent_at, "sent_at")
        _require_aware(self.expires_at, "expires_at")
        if not self.location_address.strip() or not self.location_district.strip():
            raise ValidationError("La dirección y el distrito del evento son obligatorios")
        self.extras = tuple(self.extras)

    @classmethod
    def create(
        cls,
        *,
        client_id: UUID,
        source: QuoteSource,
        event_date: date,
        event_time: time,
        location_address: str,
        location_district: str,
        package_id: UUID,
        theme_id: UUID | None = None,
        client_provides_mobility: bool,
        mobility: MobilityResult,
        liquidation: Liquidation,
        extras: Sequence[QuoteExtraLine] = (),
        now: datetime,
        deadline_hours: int,
        latitude: Decimal | None = None,
        longitude: Decimal | None = None,
        manual_request_hash: str | None = None,
        mobility_overridden: bool = False,
        mobility_override_reason: str | None = None,
    ) -> Self:
        """Nace en ``SENT`` con la liquidación congelada y vencimiento ``now + deadline_hours``."""

        sent_at = _require_aware(now, "now")
        if isinstance(deadline_hours, bool) or not isinstance(deadline_hours, int):
            raise ValidationError("deadline_hours debe ser un entero")
        if deadline_hours <= 0:
            raise ValidationError("deadline_hours debe ser mayor que cero")
        if client_provides_mobility != (mobility.scenario is MobilityScenario.EXEMPT):
            raise ValidationError(
                "La exoneración de movilidad no coincide con la movilidad resuelta"
            )
        if liquidation.mobility_amount != mobility.final_amount:
            raise ValidationError("La liquidación no coincide con la movilidad resuelta")
        extras_total = Money.zero()
        for line in extras:
            extras_total = extras_total + line.subtotal
        if extras_total > liquidation.services_subtotal:
            raise ValidationError("Los extras superan el subtotal de servicios")
        return cls(
            client_id=client_id,
            source=source,
            event_date=event_date,
            event_time=event_time,
            location_address=location_address,
            location_district=location_district,
            package_id=package_id,
            theme_id=theme_id,
            latitude=latitude,
            longitude=longitude,
            client_provides_mobility=client_provides_mobility,
            calculated_distance_km=mobility.distance_km,
            calculated_transit_minutes=mobility.duration_minutes,
            base_mobility_amount=mobility.base_amount,
            mobility_overridden=mobility_overridden,
            mobility_override_reason=mobility_override_reason,
            liquidation=liquidation,
            extras=tuple(extras),
            sent_at=sent_at,
            expires_at=sent_at + timedelta(hours=deadline_hours),
            manual_request_hash=manual_request_hash,
        )

    @property
    def is_terminal(self) -> bool:
        return self.status not in _OPEN_STATUSES

    def start_payment(self, now: datetime) -> None:
        """``SENT`` → ``PAYMENT_STARTED``; idempotente si el pago ya inició."""

        instant = _require_aware(now, "now")
        if self.status in (QuoteStatus.CONVERTED, QuoteStatus.CANCELLED):
            raise InvalidQuoteStateError(f"La cotización está {self.status.value}.")
        if self.status is QuoteStatus.EXPIRED:
            raise QuoteExpiredError("La cotización venció.")
        if self.status is QuoteStatus.PAYMENT_STARTED:
            return
        if instant >= self.expires_at:
            raise QuoteExpiredError("La cotización venció.")
        self.status = QuoteStatus.PAYMENT_STARTED

    def convert(self) -> None:
        """``PAYMENT_STARTED`` → ``CONVERTED`` (adelanto verificado)."""

        if self.status is not QuoteStatus.PAYMENT_STARTED:
            raise InvalidQuoteStateError("Solo una cotización con pago iniciado puede convertirse.")
        self.status = QuoteStatus.CONVERTED

    def expire(self, now: datetime) -> None:
        """``SENT`` o ``PAYMENT_STARTED`` → ``EXPIRED``, solo si ``now >= expires_at``."""

        instant = _require_aware(now, "now")
        if self.status not in _OPEN_STATUSES:
            raise InvalidQuoteStateError(f"La cotización está {self.status.value}.")
        if instant < self.expires_at:
            raise InvalidQuoteStateError("La cotización aún no ha vencido.")
        self.status = QuoteStatus.EXPIRED

    def cancel(self, reason: str | None = None) -> None:
        """``SENT`` o ``PAYMENT_STARTED`` → ``CANCELLED``; el motivo es opcional."""

        if self.status not in _OPEN_STATUSES:
            raise InvalidQuoteStateError(f"La cotización está {self.status.value}.")
        self.status = QuoteStatus.CANCELLED
        self.cancellation_reason = reason.strip() if reason and reason.strip() else None
