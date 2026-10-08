import pytest

from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.phone_number import PhoneNumber


@pytest.mark.parametrize(
    "raw",
    [
        "999999999",
        "51999999999",
        "+51999999999",
        "999 999 999",
        "+51 999-999-999",
        "  +51-999 999-999  ",
        "+999999999",
    ],
)
def test_parse_normalizes_peruvian_formats_to_e164(raw: str) -> None:
    assert PhoneNumber.parse(raw).value == "+51999999999"


def test_parse_keeps_foreign_country_codes() -> None:
    assert PhoneNumber.parse("+14155552671").value == "+14155552671"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "12345678",
        "+51 99999",
        "9999999999999999",
        "abc999999",
        "+51(999)999999",
        "++51999999999",
    ],
)
def test_parse_rejects_invalid_numbers(raw: str) -> None:
    with pytest.raises(ValidationError):
        PhoneNumber.parse(raw)


def test_parse_rejects_non_text() -> None:
    with pytest.raises(ValidationError):
        PhoneNumber.parse(999999999)  # type: ignore[arg-type]


def test_constructor_only_accepts_canonical_values() -> None:
    assert PhoneNumber("+51999999999").value == "+51999999999"
    with pytest.raises(ValidationError):
        PhoneNumber("999999999")


def test_digits_national_and_str() -> None:
    phone = PhoneNumber.parse("999999999")
    assert phone.digits == "51999999999"
    assert phone.national == "999999999"
    assert str(phone) == "+51999999999"
    assert PhoneNumber.parse("+14155552671").national == "+14155552671"


def test_equality_ignores_original_format() -> None:
    assert PhoneNumber.parse("999 999 999") == PhoneNumber.parse("+51999999999")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0051999999999", "+51999999999"),
        ("00 51 999-999-999", "+51999999999"),
        ("0014155552671", "+14155552671"),
    ],
)
def test_parse_treats_double_zero_as_international_prefix(raw: str, expected: str) -> None:
    assert PhoneNumber.parse(raw).value == expected


@pytest.mark.parametrize("raw", ["+0051999999999", "00999999999", "0000000000000"])
def test_parse_rejects_invalid_double_zero_shapes(raw: str) -> None:
    with pytest.raises(ValidationError):
        PhoneNumber.parse(raw)


def test_constructor_rejects_canonical_values_starting_with_zero() -> None:
    with pytest.raises(ValidationError):
        PhoneNumber("+0051999999999")
