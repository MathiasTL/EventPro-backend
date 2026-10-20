"""Servicio de dominio: umbral de shows simultáneos (RN-04, PC-03, US-10).

Cuenta el solapamiento **real** de intervalos ``[inicio, fin)`` con las ventanas de
los eventos que ya reservan cupo (con adelanto validado y no cancelados) y decide si
el nuevo show exige aprobación manual del encargado.

El llamador es responsable de entregar únicamente las ventanas que cuentan para el
umbral: solo eventos con adelanto validado y que no estén ``CANCELLED``.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.value_objects.time_window import TimeWindow


class ConcurrencyEvaluator:
    """Evalúa el umbral de concurrencia de shows solapados."""

    def __init__(self, threshold: int = 3) -> None:
        if threshold < 0:
            raise ValueError("threshold no puede ser negativo")
        self._threshold = threshold

    @property
    def threshold(self) -> int:
        """Umbral configurado (``SIMULTANEOUS_SHOWS_THRESHOLD``)."""

        return self._threshold

    def simultaneous_count(
        self, existing_windows: Sequence[TimeWindow], candidate: TimeWindow
    ) -> int:
        """Cantidad de shows simultáneos al incorporar ``candidate`` (incluido él)."""

        overlapping = sum(1 for window in existing_windows if window.overlaps(candidate))
        return 1 + overlapping

    def requires_manual_approval(
        self, existing_windows: Sequence[TimeWindow], candidate: TimeWindow
    ) -> bool:
        """Indica si el nuevo show supera el umbral y exige aprobación manual.

        Con el umbral por defecto (3), un cuarto show simultáneo devuelve ``True``;
        tres o menos devuelve ``False``.
        """

        return self.simultaneous_count(existing_windows, candidate) > self._threshold
