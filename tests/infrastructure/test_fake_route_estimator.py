from decimal import Decimal

import pytest

from app.domain.exceptions.quote_exceptions import RouteEstimationError
from app.domain.value_objects.mobility import RouteEstimate, RouteLocation
from app.infrastructure.adapters.secondary.external_services.fake_route_estimator_adapter import (
    FakeRouteEstimatorAdapter,
)

_BASE = RouteLocation(latitude=Decimal("-12.0864"), longitude=Decimal("-77.0328"))
_EVENT = RouteLocation(address="Av. Benavides 1234, Miraflores")


async def test_returns_default_round_trip_estimate() -> None:
    adapter = FakeRouteEstimatorAdapter()
    assert await adapter.estimate(_BASE, _EVENT) == RouteEstimate(Decimal("20.00"), 40)


async def test_returns_configured_estimate_and_records_calls() -> None:
    estimate = RouteEstimate(Decimal("12.50"), 25)
    adapter = FakeRouteEstimatorAdapter(estimate)
    assert await adapter.estimate(_BASE, _EVENT) == estimate
    assert adapter.calls == [(_BASE, _EVENT)]


async def test_failure_can_be_toggled() -> None:
    adapter = FakeRouteEstimatorAdapter()
    adapter.fail = True
    with pytest.raises(RouteEstimationError):
        await adapter.estimate(_BASE, _EVENT)
    adapter.fail = False
    assert (await adapter.estimate(_BASE, _EVENT)).duration_minutes == 40
