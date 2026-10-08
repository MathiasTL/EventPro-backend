from collections.abc import Iterator
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.core.config import get_settings
from app.domain.services.financial_engine import FinancialEngine
from app.domain.value_objects.mobility import MobilityZone
from app.domain.value_objects.money import Money
from app.infrastructure.adapters.secondary.external_services.fake_messaging_adapter import (
    FakeMessagingAdapter,
)
from app.infrastructure.adapters.secondary.external_services.fake_route_estimator_adapter import (
    FakeRouteEstimatorAdapter,
)
from app.infrastructure.adapters.secondary.persistence.repositories.sqlalchemy_client_repository import (  # noqa: E501
    SqlAlchemyClientRepository,
)
from app.infrastructure.adapters.secondary.persistence.repositories.sqlalchemy_quote_repository import (  # noqa: E501
    SqlAlchemyQuoteRepository,
)
from app.infrastructure.di import containers


@pytest.fixture(autouse=True)
def _fresh_caches() -> Iterator[None]:
    containers.clear_application_caches()
    get_settings.cache_clear()
    yield
    containers.clear_application_caches()
    get_settings.cache_clear()


def test_mobility_tariff_is_built_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOBILITY_ZONE_3_AMOUNT", "99.90")
    tariff = containers.get_mobility_tariff()
    assert tariff.zone_amount(MobilityZone.ZONE_3) == Money(Decimal("99.90"))
    assert tariff.rate_per_km == Money(Decimal("1.00"))
    assert containers.get_mobility_tariff() is tariff


def test_financial_engine_uses_tariff_and_advance_percent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADVANCE_PERCENT", "20")
    engine = containers.get_financial_engine()
    assert isinstance(engine, FinancialEngine)
    liquidation = engine.liquidate(
        package_price=Money(Decimal("1000.00")), extras=[], mobility_amount=Money.zero()
    )
    assert liquidation.advance_amount == Money(Decimal("200.00"))


def test_route_estimator_and_messaging_ports_default_to_fakes() -> None:
    assert isinstance(containers.get_route_estimator(), FakeRouteEstimatorAdapter)
    assert isinstance(containers.get_messaging_port(), FakeMessagingAdapter)
    assert containers.get_messaging_port() is containers.get_messaging_port()


@pytest.mark.parametrize(
    ("app_env", "expected"),
    [("development", True), ("production", False), ("staging", False), ("test", False)],
)
def test_messaging_port_logs_only_in_development(
    monkeypatch: pytest.MonkeyPatch, app_env: str, expected: bool
) -> None:
    monkeypatch.setenv("APP_ENV", app_env)
    adapter = containers.get_messaging_port()
    assert isinstance(adapter, FakeMessagingAdapter)
    assert adapter._log_messages is expected  # noqa: SLF001


def test_repositories_are_bound_to_the_request_session() -> None:
    session = AsyncMock()
    assert isinstance(containers.get_quote_repository(session), SqlAlchemyQuoteRepository)
    assert isinstance(containers.get_client_repository(session), SqlAlchemyClientRepository)
