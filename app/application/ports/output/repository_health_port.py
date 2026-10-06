from typing import Protocol


class IRepositoryHealthPort(Protocol):
    async def ping(self) -> bool:
        """True si la base de datos responde a una consulta trivial."""
