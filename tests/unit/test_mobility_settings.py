from decimal import Decimal

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.config import Settings
from app.domain.value_objects.mobility import MobilityZone
from app.domain.value_objects.money import Money
from app.infrastructure.adapters.secondary.mobility.district_zones import (
    DISTRICT_ZONES,
    normalize_district,
    zone_for_district,
)
from app.infrastructure.adapters.secondary.mobility.tariff import build_mobility_tariff

_MOBILITY_ENV = (
    "ADVANCE_DEADLINE_HOURS",
    "ADVANCE_PERCENT",
    "MOBILITY_RATE_PER_KM",
    "MOBILITY_RATE_PER_MINUTE",
    "MOBILITY_MINIMUM_AMOUNT",
    "MOBILITY_MARGIN_PERCENT",
    "MOBILITY_ZONE_1_AMOUNT",
    "MOBILITY_ZONE_2_AMOUNT",
    "MOBILITY_ZONE_3_AMOUNT",
)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in _MOBILITY_ENV:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def _settings() -> Settings:
    return Settings(secret_key="s" * 40, _env_file=None)  # type: ignore[call-arg]


def test_defaults_match_the_spec(clean_env: pytest.MonkeyPatch) -> None:
    settings = _settings()
    assert settings.advance_percent == 10
    assert settings.advance_deadline_hours == 24
    assert settings.mobility_rate_per_km == Decimal("1.00")
    assert settings.mobility_rate_per_minute == Decimal("0.30")
    assert settings.mobility_minimum_amount == Decimal("20.00")
    assert settings.mobility_margin_percent == Decimal("15")
    assert settings.mobility_zone_1_amount == Decimal("25.00")
    assert settings.mobility_zone_2_amount == Decimal("45.00")
    assert settings.mobility_zone_3_amount == Decimal("70.00")


def test_values_can_be_overridden_by_environment(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("MOBILITY_RATE_PER_KM", "1.50")
    clean_env.setenv("MOBILITY_MARGIN_PERCENT", "12.5")
    clean_env.setenv("ADVANCE_DEADLINE_HOURS", "48")
    settings = _settings()
    assert settings.mobility_rate_per_km == Decimal("1.50")
    assert settings.mobility_margin_percent == Decimal("12.5")
    assert settings.advance_deadline_hours == 48


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("MOBILITY_RATE_PER_KM", "-1"),
        ("MOBILITY_ZONE_3_AMOUNT", "-0.01"),
        ("MOBILITY_MARGIN_PERCENT", "-5"),
        ("ADVANCE_DEADLINE_HOURS", "0"),
        ("MOBILITY_RATE_PER_MINUTE", "0.255"),
        ("MOBILITY_RATE_PER_KM", "1.005"),
        ("MOBILITY_MINIMUM_AMOUNT", "20.001"),
        ("MOBILITY_ZONE_1_AMOUNT", "25.001"),
        ("MOBILITY_ZONE_2_AMOUNT", "45.001"),
        ("MOBILITY_ZONE_3_AMOUNT", "70.001"),
    ],
)
def test_invalid_values_are_rejected(clean_env: pytest.MonkeyPatch, name: str, value: str) -> None:
    clean_env.setenv(name, value)
    with pytest.raises(PydanticValidationError):
        _settings()


def test_build_mobility_tariff_from_settings(clean_env: pytest.MonkeyPatch) -> None:
    tariff = build_mobility_tariff(_settings())
    assert tariff.rate_per_km == Money(Decimal("1.00"))
    assert tariff.rate_per_minute == Money(Decimal("0.30"))
    assert tariff.minimum_amount == Money(Decimal("20.00"))
    assert tariff.margin_percent == Decimal("15")
    assert tariff.zone_amount(MobilityZone.ZONE_1) == Money(Decimal("25.00"))
    assert tariff.zone_amount(MobilityZone.ZONE_2) == Money(Decimal("45.00"))
    assert tariff.zone_amount(MobilityZone.ZONE_3) == Money(Decimal("70.00"))


def test_district_table_covers_lima_metropolitana_and_callao() -> None:
    assert len(DISTRICT_ZONES) == 50  # 43 distritos de Lima Metropolitana + 7 del Callao
    assert set(DISTRICT_ZONES.values()) == set(MobilityZone)


@pytest.mark.parametrize(
    ("district", "zone"),
    [
        ("Miraflores", MobilityZone.ZONE_1),
        ("  SAN   isidro ", MobilityZone.ZONE_1),
        ("Jesus Maria", MobilityZone.ZONE_1),
        ("Rímac", MobilityZone.ZONE_1),
        ("Cercado de Lima", MobilityZone.ZONE_1),
        ("Surco", MobilityZone.ZONE_2),
        ("Santiago de Surco", MobilityZone.ZONE_2),
        ("La Molina", MobilityZone.ZONE_2),
        ("callao", MobilityZone.ZONE_2),
        ("SJL", MobilityZone.ZONE_3),
        ("Ventanilla", MobilityZone.ZONE_3),
        ("Pachacamac", MobilityZone.ZONE_3),
    ],
)
def test_known_districts_resolve_to_their_zone(district: str, zone: MobilityZone) -> None:
    assert zone_for_district(district) is zone


@pytest.mark.parametrize("district", ["Arequipa", "", "   ", "Distrito Inventado"])
def test_unknown_district_falls_back_to_zone_three(district: str) -> None:
    assert zone_for_district(district) is MobilityZone.ZONE_3


def test_normalize_district_strips_accents_and_spaces() -> None:
    assert normalize_district("  Magdalena   del Mar ") == "magdalena del mar"
    assert normalize_district("Ñandú") == "nandu"
