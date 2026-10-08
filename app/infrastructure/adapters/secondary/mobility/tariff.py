"""Construcción de la tarifa de movilidad a partir de la configuración."""

from app.core.config import Settings
from app.domain.value_objects.mobility import MobilityTariff
from app.domain.value_objects.money import Money


def build_mobility_tariff(settings: Settings) -> MobilityTariff:
    return MobilityTariff(
        rate_per_km=Money(settings.mobility_rate_per_km),
        rate_per_minute=Money(settings.mobility_rate_per_minute),
        minimum_amount=Money(settings.mobility_minimum_amount),
        margin_percent=settings.mobility_margin_percent,
        zone_1_amount=Money(settings.mobility_zone_1_amount),
        zone_2_amount=Money(settings.mobility_zone_2_amount),
        zone_3_amount=Money(settings.mobility_zone_3_amount),
    )
