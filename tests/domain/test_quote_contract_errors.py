from dataclasses import FrozenInstanceError
from datetime import date, time

import pytest

from app.domain.exceptions.quote_exceptions import (
    AvailabilityAlternative,
    AvailabilityConflictError,
    AvailabilityRejectedError,
    ClientNotFoundError,
    QuoteNotFoundError,
    SimultaneousThresholdExceededError,
)
from app.domain.exceptions.resource_exceptions import DomainError, ResourceNotFoundError

ALTERNATIVE = AvailabilityAlternative(date(2026, 10, 15), time(18, 0))


def test_availability_conflict_exposes_code_alternatives_and_handoff() -> None:
    error = AvailabilityConflictError("Sin cupo.", alternatives=[ALTERNATIVE])
    assert error.code == "availability-conflict"
    assert error.alternatives == (ALTERNATIVE,)
    assert isinstance(error.alternatives, tuple)
    assert error.handoff_available is True
    assert str(error) == "Sin cupo."


def test_simultaneous_threshold_has_its_own_code() -> None:
    error = SimultaneousThresholdExceededError("Demasiados shows.")
    assert error.code == "simultaneous-threshold-exceeded"
    assert error.alternatives == ()


def test_both_availability_errors_share_the_rejected_base() -> None:
    for error in (
        AvailabilityConflictError("a"),
        SimultaneousThresholdExceededError("b"),
    ):
        assert isinstance(error, AvailabilityRejectedError)
        assert isinstance(error, DomainError)


def test_not_found_errors_are_resource_not_found_subclasses() -> None:
    quote = QuoteNotFoundError("No existe la cotización.")
    client = ClientNotFoundError("No existe el cliente.")
    assert isinstance(quote, ResourceNotFoundError)
    assert isinstance(client, ResourceNotFoundError)
    assert quote.code == "quote-not-found"
    assert client.code == "client-not-found"


def test_alternatives_are_hashable_and_immutable() -> None:
    assert hash(ALTERNATIVE) == hash(AvailabilityAlternative(date(2026, 10, 15), time(18, 0)))
    with pytest.raises(FrozenInstanceError):
        ALTERNATIVE.event_time = time(19, 0)  # type: ignore[misc]
