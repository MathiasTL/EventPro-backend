from datetime import datetime
from typing import Protocol


class IClockPort(Protocol):
    def utcnow(self) -> datetime:
        """Instante del servidor con zona horaria UTC."""
