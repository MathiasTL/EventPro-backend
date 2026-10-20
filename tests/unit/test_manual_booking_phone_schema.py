import pytest
from pydantic import ValidationError

from app.domain.value_objects.phone_number import PhoneNumber
from app.infrastructure.adapters.primary.web.schemas.manual_booking_schemas import ManualRequest


def _legacy_normalize(value: str) -> str:
    """Copia literal de la regla previa a PhoneNumber, para probar la equivalencia."""

    digits = value.lstrip("+")
    if len(digits) == 9:
        digits = "51" + digits
    return "+" + digits


def _payload(phone: str) -> dict[str, object]:
    return {
        "client_name": "Ana Torres",
        "event_date": "2030-01-15",
        "start_time": "21:30:00",
        "address": "Av. Benavides 1234",
        "package_id": "00000000-0000-0000-0000-000000000001",
        "client_provides_transport": True,
        "quote_id": "00000000-0000-0000-0000-000000000002",
        "phone": phone,
        "district": "Miraflores",
        "payment_method": "YAPE",
        "paid_amount": "100.00",
    }


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("999999999", "+51999999999"),
        ("51999999999", "+51999999999"),
        ("+51999999999", "+51999999999"),
        ("+14155552671", "+14155552671"),
        ("123456789012", "+123456789012"),
    ],
)
def test_schema_normalizes_exactly_as_before(raw: str, expected: str) -> None:
    request = ManualRequest(**_payload(raw))
    assert request.phone == expected
    assert request.phone == PhoneNumber.parse(raw).value


@pytest.mark.parametrize(
    "raw",
    ["999999999", "+999999999", "51999999999", "+51999999999", "1234567890", "+123456789012345"],
)
def test_schema_matches_the_previous_rule_for_every_accepted_shape(raw: str) -> None:
    assert ManualRequest(**_payload(raw)).phone == _legacy_normalize(raw)


@pytest.mark.parametrize("raw", ["999 999 999", "+51-999-999-999", "12345678", "abc", ""])
def test_schema_still_rejects_what_the_pattern_rejected(raw: str) -> None:
    with pytest.raises(ValidationError):
        ManualRequest(**_payload(raw))


def test_schema_delegates_normalization_to_phone_number(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = PhoneNumber("+51000000000")
    monkeypatch.setattr(PhoneNumber, "parse", classmethod(lambda cls, raw: sentinel))
    assert ManualRequest(**_payload("999999999")).phone == "+51000000000"


def test_schema_normalizes_international_double_zero_prefix() -> None:
    """Cambio intencional: ``00`` es el prefijo internacional y ya no se conserva como ``+00``."""

    assert ManualRequest(**_payload("0051999999999")).phone == "+51999999999"


@pytest.mark.parametrize("raw", ["+0051999999999", "00999999999"])
def test_schema_rejects_zero_led_numbers_with_a_validation_error(raw: str) -> None:
    """Cambio intencional: ``+0…`` nunca es E.164 y debe dar un error de validación de pydantic."""

    with pytest.raises(ValidationError):
        ManualRequest(**_payload(raw))
