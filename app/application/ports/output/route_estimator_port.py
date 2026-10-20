from typing import Protocol

from app.domain.value_objects.mobility import RouteEstimate, RouteLocation


class IRouteEstimatorPort(Protocol):
    async def estimate(self, origin: RouteLocation, destination: RouteLocation) -> RouteEstimate:
        """Distancia y duración de ida y vuelta; lanza RouteEstimationError si falla."""
