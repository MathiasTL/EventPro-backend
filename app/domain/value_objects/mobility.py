"""Objetos de valor de movilidad (RN-03): tarifa, ruta estimada, zona y resultado."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import IntEnum, StrEnum

from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.money import Money

_KM_STEP = Decimal("0.01")
_MAX_DISTANCE_KM = Decimal("9999.99")  # NUMERIC(6,2) en quotes.calculated_distance_km


class MobilityZone(IntEnum):
    """Zona tarifaria del distrito del evento (escenario C, contingencia)."""

    ZONE_1 = 1
    ZONE_2 = 2
    ZONE_3 = 3


class MobilityScenario(StrEnum):
    EXEMPT = "EXEMPT"
    ROUTE = "ROUTE"
    CONTINGENCY = "CONTINGENCY"


@dataclass(frozen=True)
class RouteLocation:
    """Extremo de una ruta: dirección, coordenadas o ambas."""

    address: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None

    def __post_init__(self) -> None:
        if self.address is not None:
            stripped = self.address.strip()
            if not stripped:
                raise ValidationError("address no puede estar vacío")
            object.__setattr__(self, "address", stripped)
        if (self.latitude is None) != (self.longitude is None):
            raise ValidationError("latitude y longitude deben informarse juntas")
        if self.address is None and self.latitude is None:
            raise ValidationError("La ubicación requiere dirección o coordenadas")
        if self.latitude is not None and self.longitude is not None:
            if not Decimal("-90") <= self.latitude <= Decimal("90"):
                raise ValidationError("latitude fuera de rango")
            if not Decimal("-180") <= self.longitude <= Decimal("180"):
                raise ValidationError("longitude fuera de rango")


@dataclass(frozen=True)
class RouteEstimate:
    """Distancia y duración de **ida y vuelta**; la distancia se cuantiza a 0.01 km."""

    distance_km: Decimal
    duration_minutes: int

    def __post_init__(self) -> None:
        if not isinstance(self.distance_km, Decimal) or not self.distance_km.is_finite():
            raise ValidationError("distance_km debe ser un Decimal finito")
        if isinstance(self.duration_minutes, bool) or not isinstance(self.duration_minutes, int):
            raise ValidationError("duration_minutes debe ser un entero")
        distance = self.distance_km.quantize(_KM_STEP, rounding=ROUND_HALF_UP)
        if distance < 0 or self.duration_minutes < 0:
            raise ValidationError("La distancia y la duración no pueden ser negativas")
        if distance > _MAX_DISTANCE_KM:
            raise ValidationError("distance_km supera el máximo almacenable (9999.99)")
        object.__setattr__(self, "distance_km", distance)


@dataclass(frozen=True)
class MobilityTariff:
    """Tarifa de movilidad configurable (supuestos pendientes de validar con el negocio)."""

    rate_per_km: Money
    rate_per_minute: Money
    minimum_amount: Money
    margin_percent: Decimal
    zone_1_amount: Money
    zone_2_amount: Money
    zone_3_amount: Money

    def __post_init__(self) -> None:
        amounts = (
            self.rate_per_km,
            self.rate_per_minute,
            self.minimum_amount,
            self.zone_1_amount,
            self.zone_2_amount,
            self.zone_3_amount,
        )
        for amount in amounts:
            if not isinstance(amount, Money) or amount.currency != "PEN":
                raise ValidationError("Las tarifas deben ser importes PEN")
            if amount.amount < 0:
                raise ValidationError("Las tarifas no pueden ser negativas")
        if not isinstance(self.margin_percent, Decimal) or self.margin_percent < 0:
            raise ValidationError("margin_percent debe ser un Decimal mayor o igual a cero")

    def zone_amount(self, zone: MobilityZone) -> Money:
        """Monto final fijo de la zona (no lleva margen)."""

        return {
            MobilityZone.ZONE_1: self.zone_1_amount,
            MobilityZone.ZONE_2: self.zone_2_amount,
            MobilityZone.ZONE_3: self.zone_3_amount,
        }[zone]


@dataclass(frozen=True)
class MobilityResult:
    """Movilidad resuelta; ``distance_km`` y ``duration_minutes`` son None en exención y zona."""

    scenario: MobilityScenario
    distance_km: Decimal | None
    duration_minutes: int | None
    base_amount: Money
    final_amount: Money
