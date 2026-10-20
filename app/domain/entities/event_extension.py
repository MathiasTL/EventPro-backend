"""Extensión cobrada de un evento; independiente de HTTP y persistencia."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from app.domain.entities.payment import PaymentMethod
from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.money import Money

MAX_AMOUNT = Decimal("99999999.99")
MAX_MINUTES = 2147483647


def validate_extension_terms(
    minutes: int, amount: Decimal, method: PaymentMethod, reference: str | None
) -> Money:
    """Valida la solicitud pura antes de consultar persistencia."""
    validate_extra_minutes(minutes)
    if (
        not isinstance(amount, Decimal)
        or not amount.is_finite()
        or not 0 < amount <= MAX_AMOUNT
        or amount != amount.quantize(Decimal("0.01"))
    ):
        raise ValidationError("El importe debe ser positivo, finito y tener hasta dos decimales.")
    if not isinstance(method, PaymentMethod):
        raise ValidationError("El medio de pago no es válido.")
    if reference is not None and (not reference.strip() or len(reference) > 60):
        raise ValidationError("La referencia debe contener entre 1 y 60 caracteres.")
    return Money(amount)


def validate_extra_minutes(value: int, *, allow_zero: bool = False) -> None:
    minimum = 0 if allow_zero else 1
    if type(value) is not int or not minimum <= value <= MAX_MINUTES:
        raise ValidationError(f"Los minutos deben ser enteros entre {minimum} y {MAX_MINUTES}.")


def validate_extension_amount(value: Money, *, allow_zero: bool = False) -> None:
    if (
        not isinstance(value, Money)
        or value.currency != "PEN"
        or not value.amount.is_finite()
        or value.amount < 0
        or (not allow_zero and value.amount == 0)
        or value.amount > MAX_AMOUNT
    ):
        raise ValidationError("El importe debe ser finito, positivo y representable en PEN.")


@dataclass(frozen=True, kw_only=True)
class EventExtension:
    event_id: UUID
    payment_id: UUID
    extra_minutes: int
    agreed_rate: Money
    requested_at: datetime
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not all(isinstance(value, UUID) for value in (self.id, self.event_id, self.payment_id)):
            raise ValidationError("La extensión, el evento y el pago deben tener IDs UUID.")
        validate_extra_minutes(self.extra_minutes)
        validate_extension_amount(self.agreed_rate)
        if self.requested_at.tzinfo is None or self.requested_at.utcoffset() is None:
            raise ValidationError("La fecha de la extensión debe incluir zona horaria.")
        object.__setattr__(self, "requested_at", self.requested_at.astimezone(UTC))
