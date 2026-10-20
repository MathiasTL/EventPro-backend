from typing import Protocol


class ICachePort(Protocol):
    async def ping(self) -> bool:
        """True si Redis responde a un PING."""
