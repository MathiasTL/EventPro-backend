from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.application.dtos.financial_dto import FinancialPnlRequest
from app.application.ports.input.financial_report_port import (
    IGetFinancialCollectionsPort,
    IGetFinancialPnlPort,
)
from app.domain.exceptions.financial_exceptions import FinancialDataInconsistentError
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.primary.web.deps import AuthContext, require_role
from app.infrastructure.adapters.primary.web.problem import ProblemError
from app.infrastructure.adapters.primary.web.schemas.financial_schemas import (
    FinancialCollectionsResponse,
    FinancialPnlQuery,
    FinancialPnlResponse,
)
from app.infrastructure.di.containers import (
    get_financial_collections_use_case,
    get_financial_pnl_use_case,
)

router = APIRouter(prefix="/reports/financial", tags=["Reportes financieros"])


@router.get(
    "/pnl",
    response_model=FinancialPnlResponse,
    summary="Consolidar ingresos, costos y utilidad de eventos liquidados",
    description=(
        "US-21: período por fecha local del evento, costos congelados al liquidar. "
        "Ejemplo mensual: period_type=MONTHLY&year=2026&month=10. "
        "Ejemplo semanal: period_type=WEEKLY&year=2026&week=42."
    ),
    responses={
        401: {"description": "Autenticación requerida"},
        403: {"description": "Rol no permitido"},
        409: {"description": "Datos financieros incompletos o inconsistentes"},
        422: {"description": "Período inválido"},
    },
)
async def get_financial_pnl(
    query: Annotated[FinancialPnlQuery, Query()],
    context: Annotated[AuthContext, Depends(require_role(Role.ENCARGADO, Role.SUPERADMIN))],
    use_case: Annotated[IGetFinancialPnlPort, Depends(get_financial_pnl_use_case)],
) -> FinancialPnlResponse:
    try:
        result = await use_case.execute(
            FinancialPnlRequest(query.period_type, query.year, query.month, query.week)
        )
    except FinancialDataInconsistentError as exc:
        raise ProblemError(409, exc.code, "Conflicto", str(exc)) from exc
    return FinancialPnlResponse.model_validate(result)


@router.get(
    "/collections",
    response_model=FinancialCollectionsResponse,
    summary="Consultar cobros del período y saldos por cobrar",
    description=(
        "RF-24.1: movimientos de pagos por fecha local de Lima y saldo de eventos "
        "no liquidados por fecha del evento. Comparte el período del P&L."
    ),
    responses={
        401: {"description": "Autenticación requerida"},
        403: {"description": "Rol no permitido"},
        422: {"description": "Período inválido"},
    },
)
async def get_financial_collections(
    query: Annotated[FinancialPnlQuery, Query()],
    context: Annotated[AuthContext, Depends(require_role(Role.ENCARGADO, Role.SUPERADMIN))],
    use_case: Annotated[IGetFinancialCollectionsPort, Depends(get_financial_collections_use_case)],
) -> FinancialCollectionsResponse:
    result = await use_case.execute(
        FinancialPnlRequest(query.period_type, query.year, query.month, query.week)
    )
    return FinancialCollectionsResponse.model_validate(result)
