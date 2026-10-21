from app.application.dtos.client_dto import ClientDTO, FindClientsFilter
from app.application.dtos.page_dto import PageDTO
from app.application.ports.output.client_repository_port import IClientRepositoryPort


class FindClientsUseCase:
    def __init__(self, clients: IClientRepositoryPort) -> None:
        self._clients = clients

    async def execute(self, filters: FindClientsFilter) -> PageDTO[ClientDTO]:
        return await self._clients.find(filters)
