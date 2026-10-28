from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.application.dtos.dashboard_dto import ExecutiveDashboardRequest
from app.application.ports.input.dashboard_port import IGetExecutiveDashboardPort
from app.domain.exceptions.financial_exceptions import FinancialDataInconsistentError
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.primary.web.deps import AuthContext, require_role
from app.infrastructure.adapters.primary.web.problem import ProblemError
from app.infrastructure.adapters.primary.web.schemas.dashboard_schemas import (
    ExecutiveDashboardQuery,
    ExecutiveDashboardResponse,
)
from app.infrastructure.di.containers import get_executive_dashboard_use_case

router = APIRouter(prefix="/reports", tags=["Reportes financieros"])


@router.get(
    "/dashboard",
    response_model=ExecutiveDashboardResponse,
    summary="Consultar indicadores ejecutivos de eventos liquidados",
    description=(
        "US-22: importes congelados, por fecha local del servicio. "
        "compare_months=3 devuelve tres meses previos más el seleccionado."
    ),
    responses={
        401: {"description": "Autenticación requerida"},
        403: {"description": "Rol no permitido"},
        409: {"description": "Datos financieros incompletos o inconsistentes"},
        422: {"description": "Ventana mensual inválida"},
    },
)
async def get_executive_dashboard(
    query: Annotated[ExecutiveDashboardQuery, Query()],
    context: Annotated[AuthContext, Depends(require_role(Role.SUPERADMIN, Role.ENCARGADO))],
    use_case: Annotated[IGetExecutiveDashboardPort, Depends(get_executive_dashboard_use_case)],
) -> ExecutiveDashboardResponse:
    try:
        result = await use_case.execute(
            ExecutiveDashboardRequest(query.year, query.month, query.compare_months)
        )
    except FinancialDataInconsistentError as exc:
        raise ProblemError(409, exc.code, "Conflicto", str(exc)) from exc
    return ExecutiveDashboardResponse.model_validate(result)
