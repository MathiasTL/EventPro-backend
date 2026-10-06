"""Agregado Event: datos operativos e invariantes puras del cronograma.

La validación del adelanto que origina un evento pertenece al caso de uso de E5.
La entidad también permite rehidratar los estados existentes desde persistencia.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID, uuid4

from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.event_status import EventStatus
from app.domain.value_objects.money import Money
from app.domain.value_objects.time_window import TimeWindow


@dataclass(kw_only=True)
class Event:
    event_code: str
    quote_id: UUID
    event_date: date
    start_time: time
    end_time: time
    address: str
    district: str
    total_services_amount: Money
    total_mobility_amount: Money
    final_total_amount: Money
    id: UUID = field(default_factory=uuid4)
    client_observations: str | None = None
    status: EventStatus = EventStatus.AWAITING_SIGNATURE
    advance_paid: Money = field(default_factory=Money.zero)
    pre_show_balance_paid: Money = field(default_factory=Money.zero)
    extra_hours_amount: Money = field(default_factory=Money.zero)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        for name, limit in (("event_code", 30), ("address", 255), ("district", 80)):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                raise ValidationError(f"{name} debe contener entre 1 y {limit} caracteres")
        if not isinstance(self.status, EventStatus):
            raise ValidationError("status debe ser un EventStatus válido")
        for name in (
            "total_services_amount",
            "total_mobility_amount",
            "final_total_amount",
            "advance_paid",
            "pre_show_balance_paid",
            "extra_hours_amount",
        ):
            amount = getattr(self, name)
            if (
                not isinstance(amount, Money)
                or amount.currency != "PEN"
                or not amount.amount.is_finite()
                or amount.amount < 0
            ):
                raise ValidationError(f"{name} debe ser un importe no negativo en PEN")
        if self.start_time.tzinfo is not None or self.end_time.tzinfo is not None:
            raise ValidationError("Las horas del evento deben ser locales, sin zona horaria")
        if self.start_time == self.end_time:
            raise ValidationError("El evento debe tener una duración mayor que cero")

    @property
    def time_window(self) -> TimeWindow:
        """Ventana local: un fin anterior al inicio pertenece al día siguiente."""
        start = datetime.combine(self.event_date, self.start_time)
        end = datetime.combine(self.event_date, self.end_time)
        if end < start:
            end += timedelta(days=1)
        return TimeWindow(start, end)

    @property
    def pending_balance_to_collect(self) -> Money:
        """Saldo pre-show pendiente; final_total_amount ya incluye el total final."""
        remaining = self.final_total_amount - self.advance_paid - self.pre_show_balance_paid
        return remaining if remaining.amount > 0 else Money.zero()
