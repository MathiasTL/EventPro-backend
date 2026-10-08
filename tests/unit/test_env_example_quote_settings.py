""".env.example debe documentar los mismos valores iniciales que Settings."""

from decimal import Decimal
from pathlib import Path

import pytest

from app.core.config import Settings

_ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"

_FIELDS = (
    "advance_percent",
    "advance_deadline_hours",
    "mobility_rate_per_km",
    "mobility_rate_per_minute",
    "mobility_minimum_amount",
    "mobility_margin_percent",
    "mobility_zone_1_amount",
    "mobility_zone_2_amount",
    "mobility_zone_3_amount",
)


def _example_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in _ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


@pytest.mark.parametrize("field", _FIELDS)
def test_env_example_documents_the_settings_default(field: str) -> None:
    example = _example_values()
    assert field.upper() in example, f"{field.upper()} falta en .env.example"
    default = Settings.model_fields[field].default
    assert Decimal(example[field.upper()]) == Decimal(default)
