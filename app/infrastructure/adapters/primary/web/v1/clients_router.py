"""US-25: lectura de clientes reales, restringida al personal administrativo."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.application.dtos.client_dto import ClientDetailDTO, ClientDTO, FindClientsFilter
from app.application.dtos.page_dto import PageDTO
from app.application.ports.input.client_read_port import IFindClientsPort, IGetClientPort
from app.domain.exceptions.quote_exceptions import ClientNotFoundError
from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.primary.web.deps import AuthContext, require_role
from app.infrastructure.adapters.primary.web.problem import quote_error_to_problem
from app.infrastructure.di import containers

router = APIRouter(prefix="/clients", tags=["Clientes"])
Staff = Annotated[AuthContext, Depends(require_role(Role.ENCARGADO, Role.SUPERADMIN))]


@router.get("", response_model=PageDTO[ClientDTO])
async def find_clients(
    context: Staff,
    use_case: Annotated[IFindClientsPort, Depends(containers.get_find_clients_use_case)],
    q: str | None = None,
    phone: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PageDTO[ClientDTO]:
    try:
        return await use_case.execute(FindClientsFilter(q, phone, page, page_size))
    except ValidationError as exc:
        raise quote_error_to_problem(exc) from exc


@router.get("/{client_id}", response_model=ClientDetailDTO)
async def get_client(
    client_id: UUID,
    context: Staff,
    use_case: Annotated[IGetClientPort, Depends(containers.get_client_use_case)],
) -> ClientDetailDTO:
    try:
        return await use_case.execute(client_id)
    except ClientNotFoundError as exc:
        raise quote_error_to_problem(exc) from exc
