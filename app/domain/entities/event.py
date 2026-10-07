"""Agregado Event: datos operativos e invariantes puras del cronograma.

La validación del adelanto que origina un evento pertenece al caso de uso de E5.
La entidad también permite rehidratar los estados existentes desde persistencia.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID, uuid4

from app.domain.entities.event_extension import (
    EventExtension,
    validate_extension_amount,
    validate_extra_minutes,
)
from app.domain.exceptions.event_exceptions import (
    BalancePendingError,
    ExtensionPaymentMismatchError,
    InvalidEventStateError,
)
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
    actual_start_time: datetime | None = None
    extra_minutes_total: int = 0
    legacy_extra_hours_amount: Money = field(default_factory=Money.zero)

    def __post_init__(self) -> None:
        validate_extra_minutes(self.extra_minutes_total, allow_zero=True)
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
            "legacy_extra_hours_amount",
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

    def validate_start_state(self) -> None:
        """Rechaza estados incompatibles antes de consultar dependencias externas."""
        if (
            self.status not in (EventStatus.SCHEDULED, EventStatus.AWAITING_BALANCE)
            or self.actual_start_time is not None
        ):
            raise InvalidEventStateError(
                "Solo se puede iniciar un evento SCHEDULED o AWAITING_BALANCE sin inicio previo."
            )

    def start(self, *, verified_pre_show_amount: Money, started_at: datetime) -> None:
        """Inicia con el total BALANCE verificado, sin acumular nuevamente el saldo."""
        self.validate_start_state()
        if (
            not isinstance(verified_pre_show_amount, Money)
            or verified_pre_show_amount.currency != "PEN"
            or not verified_pre_show_amount.amount.is_finite()
            or verified_pre_show_amount.amount < 0
        ):
            raise ValidationError("El saldo verificado debe ser un importe no negativo en PEN")
        if self.advance_paid + verified_pre_show_amount < self.final_total_amount:
            raise BalancePendingError(
                "Se requiere verificar el 100% del saldo de servicios y movilidad antes de iniciar."
            )
        if started_at.tzinfo is None or started_at.utcoffset() is None:
            raise ValidationError("La hora real de inicio debe incluir zona horaria")
        actual_start_time = started_at.astimezone(UTC)
        # Todas las guardas preceden a las mutaciones del agregado.
        self.pre_show_balance_paid = verified_pre_show_amount
        self.status = EventStatus.IN_PROGRESS
        self.actual_start_time = actual_start_time

    @property
    def extended_time_window(self) -> TimeWindow:
        """Alias compatible de la ventana operativa."""
        return self.time_window

    def window_with_extra_minutes(self, minutes: int) -> TimeWindow:
        validate_extra_minutes(minutes, allow_zero=True)
        try:
            original = self.scheduled_time_window
            return TimeWindow(original.start, original.end + timedelta(minutes=minutes))
        except OverflowError as exc:
            raise ValidationError(
                "El horario extendido excede el rango de fechas permitido."
            ) from exc

    def validate_operating_state(self) -> None:
        if self.status not in (EventStatus.IN_PROGRESS, EventStatus.EXTENDED):
            raise InvalidEventStateError("Solo se admite un evento IN_PROGRESS o EXTENDED.")

    def extend(
        self,
        *,
        extra_minutes: int,
        agreed_rate: Money,
        payment_id: UUID,
        requested_at: datetime,
    ) -> EventExtension:
        self.validate_operating_state()
        extension = EventExtension(
            event_id=self.id,
            payment_id=payment_id,
            extra_minutes=extra_minutes,
            agreed_rate=agreed_rate,
            requested_at=requested_at,
        )
        minutes = self.extra_minutes_total + extra_minutes
        validate_extra_minutes(minutes)
        extra_amount = self.extra_hours_amount + agreed_rate
        final_amount = self.final_total_amount + agreed_rate
        validate_extension_amount(extra_amount)
        validate_extension_amount(final_amount)
        self.window_with_extra_minutes(minutes)
        self.extra_minutes_total = minutes
        self.extra_hours_amount = extra_amount
        self.final_total_amount = final_amount
        self.status = EventStatus.EXTENDED
        return extension

    def settle(self, *, verified_extension_amount: Money, verified_extra_minutes: int) -> None:
        self.validate_operating_state()
        validate_extension_amount(verified_extension_amount, allow_zero=True)
        validate_extra_minutes(verified_extra_minutes, allow_zero=True)
        if (
            self.legacy_extra_hours_amount + verified_extension_amount != self.extra_hours_amount
            or verified_extra_minutes != self.extra_minutes_total
        ):
            raise ExtensionPaymentMismatchError(
                "Las extensiones no coinciden con sus cobros verificados."
            )
        if (
            self.advance_paid
            + self.pre_show_balance_paid
            + self.legacy_extra_hours_amount
            + verified_extension_amount
            < self.final_total_amount
        ):
            raise BalancePendingError("Se requiere cubrir el total final antes de liquidar.")
        self.status = EventStatus.SETTLED

    @property
    def time_window(self) -> TimeWindow:
        """Ventana operativa usada por cronograma y disponibilidad."""
        return self.window_with_extra_minutes(self.extra_minutes_total)

    @property
    def scheduled_time_window(self) -> TimeWindow:
        """Ventana local: un fin anterior al inicio pertenece al día siguiente."""
        start = datetime.combine(self.event_date, self.start_time)
        end = datetime.combine(self.event_date, self.end_time)
        if end < start:
            end += timedelta(days=1)
        return TimeWindow(start, end)

    @property
    def pending_balance_to_collect(self) -> Money:
        """Saldo pendiente sin volver a cobrar las extensiones ya registradas."""
        remaining = (
            self.final_total_amount
            - self.advance_paid
            - self.pre_show_balance_paid
            - self.extra_hours_amount
        )
        return remaining if remaining.amount > 0 else Money.zero()
