"""FinancialEngine: movilidad (RN-03) y liquidación (RN-01, RN-02). Funciones puras."""

from collections.abc import Sequence
from decimal import Decimal

from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.liquidation import ExtraCharge, Liquidation
from app.domain.value_objects.mobility import (
    MobilityResult,
    MobilityScenario,
    MobilityTariff,
    MobilityZone,
    RouteEstimate,
)
from app.domain.value_objects.money import Money

_HUNDRED = Decimal(100)


class FinancialEngine:
    """Cálculo determinista; todo importe es ``Money`` (0.01, ROUND_HALF_UP)."""

    def __init__(self, *, tariff: MobilityTariff, advance_percent: int) -> None:
        if isinstance(advance_percent, bool) or not isinstance(advance_percent, int):
            raise ValidationError("advance_percent debe ser un entero")
        if not 0 < advance_percent <= 100:
            raise ValidationError("advance_percent debe estar entre 1 y 100")
        self._tariff = tariff
        self._advance_percent = Decimal(advance_percent)

    def mobility(self, estimate: RouteEstimate) -> MobilityResult:
        """Escenario A: ``max(D × tarifa_km + T × tarifa_minuto, mínimo) × (1 + margen / 100)``."""

        raw = (
            self._tariff.rate_per_km.amount * estimate.distance_km
            + self._tariff.rate_per_minute.amount * Decimal(estimate.duration_minutes)
        )
        base = max(Money(raw), self._tariff.minimum_amount)
        final = Money(base.amount * (_HUNDRED + self._tariff.margin_percent) / _HUNDRED)
        return MobilityResult(
            scenario=MobilityScenario.ROUTE,
            distance_km=estimate.distance_km,
            duration_minutes=estimate.duration_minutes,
            base_amount=base,
            final_amount=final,
        )

    def contingency(self, zone: MobilityZone) -> MobilityResult:
        """Escenario C: monto fijo de la zona, ya final (sin margen); km y minutos en None."""

        amount = self._tariff.zone_amount(zone)
        return MobilityResult(
            scenario=MobilityScenario.CONTINGENCY,
            distance_km=None,
            duration_minutes=None,
            base_amount=amount,
            final_amount=amount,
        )

    def resolve_mobility(
        self,
        *,
        client_provides_mobility: bool,
        estimate: RouteEstimate | None,
        zone: MobilityZone,
    ) -> MobilityResult:
        """Exención (RF-06), estimador (A) o contingencia por zona (C), en ese orden."""

        if client_provides_mobility:
            return MobilityResult(
                scenario=MobilityScenario.EXEMPT,
                distance_km=None,
                duration_minutes=None,
                base_amount=Money.zero(),
                final_amount=Money.zero(),
            )
        if estimate is not None:
            return self.mobility(estimate)
        return self.contingency(zone)

    def liquidate(
        self,
        *,
        package_price: Money,
        extras: Sequence[ExtraCharge],
        mobility_amount: Money,
    ) -> Liquidation:
        """Total, adelanto sobre servicios (RN-01) y saldo con movilidad al 100 % (RN-02)."""

        if package_price.currency != "PEN" or mobility_amount.currency != "PEN":
            raise ValidationError("La liquidación solo admite importes PEN")
        if package_price.amount <= 0:
            raise ValidationError("El precio del paquete debe ser mayor que cero")
        if mobility_amount.amount < 0:
            raise ValidationError("La movilidad no puede ser negativa")
        services = package_price
        for extra in extras:
            services = services + extra.subtotal
        advance = Money(services.amount * self._advance_percent / _HUNDRED)
        total = services + mobility_amount
        return Liquidation(
            services_subtotal=services,
            mobility_amount=mobility_amount,
            total_amount=total,
            advance_amount=advance,
            pending_balance=total - advance,
            balance_services=services - advance,
            balance_mobility=mobility_amount,
        )
