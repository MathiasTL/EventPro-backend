"""Servicio de dominio: intervalo mínimo de tránsito entre shows sucesivos.

RN-05: para un mismo elenco en el mismo día, el intervalo mínimo entre el fin del
show anterior y el inicio del siguiente es el **tiempo de tránsito** (Google Maps)
más el **margen de desarme y descanso** (``TRANSIT_REST_BUFFER_MINUTES``, por defecto
30 min). Si la holgura real es menor, la asignación automática se rechaza.

RF-22 / US-20: el encargado puede sobrescribir el intervalo sugerido (acortarlo o
extenderlo); cuando lo hace, se usa su valor en lugar del calculado.
"""

from __future__ import annotations

from app.domain.value_objects.time_window import TimeWindow


class TravelIntervalService:
    """Calcula y valida el intervalo de traslado entre shows de un mismo elenco."""

    def __init__(self, rest_buffer_minutes: int = 30) -> None:
        if rest_buffer_minutes < 0:
            raise ValueError("rest_buffer_minutes no puede ser negativo")
        self._rest_buffer_minutes = rest_buffer_minutes

    @property
    def rest_buffer_minutes(self) -> int:
        """Margen de desarme y descanso configurado."""

        return self._rest_buffer_minutes

    def required_interval_minutes(
        self, transit_minutes: int, override_minutes: int | None = None
    ) -> int:
        """Intervalo mínimo requerido entre dos shows.

        Si ``override_minutes`` está presente (ajuste del encargado, RF-22), se usa tal
        cual; en caso contrario es ``tránsito + margen de descanso``.
        """

        if transit_minutes < 0:
            raise ValueError("transit_minutes no puede ser negativo")
        if override_minutes is not None:
            if override_minutes < 0:
                raise ValueError("override_minutes no puede ser negativo")
            return override_minutes
        return transit_minutes + self._rest_buffer_minutes

    def is_gap_feasible(
        self,
        gap_minutes: int,
        transit_minutes: int,
        override_minutes: int | None = None,
    ) -> bool:
        """Indica si una holgura real (en minutos) cubre el intervalo requerido."""

        return gap_minutes >= self.required_interval_minutes(transit_minutes, override_minutes)

    def is_feasible(
        self,
        previous: TimeWindow,
        following: TimeWindow,
        transit_minutes: int,
        override_minutes: int | None = None,
    ) -> bool:
        """Indica si el traslado entre dos shows del mismo elenco es viable."""

        return self.is_gap_feasible(
            previous.gap_minutes_before(following), transit_minutes, override_minutes
        )
