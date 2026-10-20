from typing import Protocol
from uuid import UUID

from app.application.dtos.client_dto import ClientDetailDTO, ClientDTO, FindClientsFilter
from app.application.dtos.page_dto import PageDTO


class IFindClientsPort(Protocol):
    async def execute(self, filters: FindClientsFilter) -> PageDTO[ClientDTO]:
        """Búsqueda paginada por texto (nombre o teléfono) o por teléfono exacto."""


class IGetClientPort(Protocol):
    async def execute(self, client_id: UUID) -> ClientDetailDTO:
        """Ficha del cliente con el resumen de sus cotizaciones; lanza ``ClientNotFoundError``."""
