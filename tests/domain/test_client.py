from uuid import UUID

import pytest

from app.domain.entities.client import Client
from app.domain.exceptions.quote_exceptions import (
    InvalidQuoteStateError,
    QuoteExpiredError,
    RouteEstimationError,
)
from app.domain.exceptions.resource_exceptions import DomainError, ValidationError
from app.domain.value_objects.phone_number import PhoneNumber

_PHONE = PhoneNumber.parse("999999999")


def test_client_defaults_and_trims_name() -> None:
    client = Client(phone=_PHONE, full_name="  Ana Torres  ")
    assert client.full_name == "Ana Torres"
    assert client.dni is None and client.ruc is None
    assert isinstance(client.id, UUID)
    assert client.created_at.tzinfo is not None


def test_client_accepts_valid_dni_and_ruc() -> None:
    client = Client(phone=_PHONE, full_name="Ana", dni="12345678", ruc="20123456789")
    assert client.dni == "12345678"
    assert client.ruc == "20123456789"


@pytest.mark.parametrize("dni", ["1234567", "123456789", "1234567a", "", "１２３４５６７８"])
def test_client_rejects_invalid_dni(dni: str) -> None:
    with pytest.raises(ValidationError):
        Client(phone=_PHONE, full_name="Ana", dni=dni)


@pytest.mark.parametrize("ruc", ["2012345678", "201234567890", "2012345678a", ""])
def test_client_rejects_invalid_ruc(ruc: str) -> None:
    with pytest.raises(ValidationError):
        Client(phone=_PHONE, full_name="Ana", ruc=ruc)


@pytest.mark.parametrize("name", ["", "   ", "x" * 121])
def test_client_rejects_invalid_name(name: str) -> None:
    with pytest.raises(ValidationError):
        Client(phone=_PHONE, full_name=name)


def test_client_requires_phone_number_value_object() -> None:
    with pytest.raises(ValidationError):
        Client(phone="+51999999999", full_name="Ana")  # type: ignore[arg-type]


def test_quote_errors_expose_stable_codes() -> None:
    assert InvalidQuoteStateError.code == "invalid-quote-state"
    assert QuoteExpiredError.code == "quote-expired"
    assert RouteEstimationError.code == "route-estimation-failed"
    assert issubclass(QuoteExpiredError, DomainError)
