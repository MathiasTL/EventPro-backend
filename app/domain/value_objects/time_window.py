"""Objeto de valor ``TimeWindow``: intervalo de tiempo semiabierto ``[inicio, fin)``.

Modela la ventana de un evento (``fin = inicio + duración del paquete``) y determina
el **solape real de intervalos** que exige RN-04: dos ventanas son simultáneas solo si
sus intervalos se intersecan; dos ventanas contiguas (una termina exactamente cuando
la otra empieza) **no** se solapan. Es inmutable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TimeWindow:
    """Intervalo de tiempo semiabierto ``[start, end)``."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError("TimeWindow requiere end posterior a start")

    @property
    def duration_minutes(self) -> int:
        """Duración de la ventana en minutos completos."""

        return int((self.end - self.start).total_seconds() // 60)

    def overlaps(self, other: TimeWindow) -> bool:
        """Indica si ambas ventanas se solapan con la semántica ``[inicio, fin)``."""

        return self.start < other.end and other.start < self.end

    def is_adjacent(self, other: TimeWindow) -> bool:
        """Indica si una ventana termina exactamente cuando la otra empieza."""

        return self.end == other.start or other.end == self.start

    def gap_minutes_before(self, other: TimeWindow) -> int:
        """Minutos de holgura entre el fin de esta ventana y el inicio de ``other``.

        Puede ser negativo si ``other`` empieza antes de que termine esta ventana.
        """

        return int((other.start - self.end).total_seconds() // 60)
