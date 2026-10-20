"""Estimador de rutas falso: respuesta fija o fallo simulado, sin red ni proveedor."""

from decimal import Decimal

from app.domain.exceptions.quote_exceptions import RouteEstimationError
from app.domain.value_objects.mobility import RouteEstimate, RouteLocation


class FakeRouteEstimatorAdapter:
    def __init__(
        self,
        estimate: RouteEstimate | None = None,
        *,
        fail: bool = False,
    ) -> None:
        self._estimate = estimate or RouteEstimate(Decimal("20.00"), 40)
        self.fail = fail
        self.calls: list[tuple[RouteLocation, RouteLocation]] = []

    async def estimate(self, origin: RouteLocation, destination: RouteLocation) -> RouteEstimate:
        self.calls.append((origin, destination))
        if self.fail:
            raise RouteEstimationError("El estimador de rutas no está disponible.")
        return self._estimate
