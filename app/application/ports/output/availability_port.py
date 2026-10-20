"""Puerto de salida de verificación de disponibilidad (E3).

Contrato que consumen el cotizador (E1) antes de confirmar una cotización y la
asignación de elencos (E6). Encapsula el motor de disponibilidad (inventario,
umbral de shows simultáneos y tránsito entre shows) y los locks distribuidos.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.dtos.availability_dto import (
    AvailabilityRequest,
    AvailabilityResult,
    CrewTransitRequest,
    CrewTransitResult,
)


class IAvailabilityPort(ABC):
    """Verificación de disponibilidad de recursos y de tránsito de elencos."""

    @abstractmethod
    async def check_availability(self, request: AvailabilityRequest) -> AvailabilityResult:
        """Verifica inventario y umbral de shows simultáneos para un show solicitado.

        Devuelve ``CONFLICT`` si el stock no cubre el paquete, o
        ``REQUIRES_MANUAL_APPROVAL`` si se supera ``SIMULTANEOUS_SHOWS_THRESHOLD``.
        """

    @abstractmethod
    async def check_crew_transit(self, request: CrewTransitRequest) -> CrewTransitResult:
        """Valida el intervalo mínimo de tránsito entre shows de un mismo elenco."""
