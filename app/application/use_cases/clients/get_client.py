from uuid import UUID

from app.application.dtos.client_dto import ClientDetailDTO
from app.application.ports.output.client_repository_port import IClientRepositoryPort
from app.domain.exceptions.quote_exceptions import ClientNotFoundError


class GetClientUseCase:
    def __init__(self, clients: IClientRepositoryPort) -> None:
        self._clients = clients

    async def execute(self, client_id: UUID) -> ClientDetailDTO:
        detail = await self._clients.get_detail(client_id)
        if detail is None:
            raise ClientNotFoundError("El cliente solicitado no existe.")
        return detail
