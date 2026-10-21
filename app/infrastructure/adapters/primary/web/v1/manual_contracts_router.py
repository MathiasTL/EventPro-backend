import hashlib
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Header, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.budget_dto import BudgetInput
from app.application.dtos.manual_contract_dto import ManualContractInput
from app.application.use_cases.contract.create_manual_contract import (
    CreateManualContract,
    InvalidAdvanceAmount,
)
from app.core.config import get_settings
from app.domain.exceptions.resource_exceptions import DomainError
from app.infrastructure.adapters.primary.web.problem import ProblemError
from app.infrastructure.adapters.primary.web.schemas.manual_contract_schemas import (
    ManualContractRequest,
)
from app.infrastructure.adapters.primary.web.v1.contracts_router import Staff, problem
from app.infrastructure.adapters.secondary.mobility.district_zones import zone_for_district
from app.infrastructure.adapters.secondary.mobility.tariff import build_mobility_tariff
from app.infrastructure.adapters.secondary.persistence.database import get_contract_write_session
from app.infrastructure.di.containers import get_create_manual_contract_use_case

router = APIRouter(prefix="/contracts", tags=["Contratos"])


@router.post("/manual", status_code=201)
async def create_manual_contract(
    context: Staff,
    transaction: Annotated[AsyncSession, Depends(get_contract_write_session, scope="function")],
    use_case: Annotated[CreateManualContract, Depends(get_create_manual_contract_use_case)],
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    payload: Annotated[str, Form(max_length=30000)],
    advance_evidence_file: Annotated[UploadFile, File()],
) -> JSONResponse:
    try:
        request = ManualContractRequest.model_validate_json(payload)
    except ValueError as exc:
        raise ProblemError(
            422, "validation-error", "Datos inválidos", "Revisa los datos del contrato manual"
        ) from exc
    receipt = await advance_evidence_file.read(5 * 1024 * 1024 + 1)
    canonical = request.model_dump_json() + hashlib.sha256(receipt).hexdigest()
    fingerprint = hashlib.sha256(canonical.encode()).hexdigest()
    mobility = (
        Decimal(0)
        if request.client_provides_mobility
        else request.agreed_mobility_amount
        if request.agreed_mobility_amount is not None
        else build_mobility_tariff(get_settings())
        .zone_amount(zone_for_district(request.location_district))
        .amount
    )
    reason = request.mobility_override_reason or "Tarifa de contingencia por zona (RN-03)"
    try:
        booking, contract, created = await use_case.execute(
            ManualContractInput(
                quote_id=idempotency_key,
                request_hash=fingerprint,
                budget=BudgetInput(
                    request.client.full_name,
                    request.event_date,
                    request.event_time,
                    request.location_address,
                    request.package_id,
                    request.theme_id,
                    tuple(extra.extra_id for extra in request.extras),
                    request.client_provides_mobility,
                    mobility,
                    reason,
                ),
                phone=request.client.phone,
                district=request.location_district,
                dni=request.client.dni,
                ruc=request.client.ruc,
                quantities=tuple((extra.extra_id, extra.quantity) for extra in request.extras),
                agreed_services=request.agreed_services_subtotal,
                agreed_reason=request.agreed_services_reason,
                payment_method=request.advance.payment_method,
                advance=request.advance.amount,
                reference=request.advance.transaction_reference,
                observations=request.client_observations,
                clauses=request.custom_clauses,
                issue=request.issue_contract,
                receipt=receipt,
                receipt_type=advance_evidence_file.content_type or "",
                receipt_name=advance_evidence_file.filename or "evidence",
            ),
            context.user_id,
        )
        return JSONResponse(
            jsonable_encoder(
                {
                    "quote_id": booking.quote_id,
                    "client_id": booking.client_id,
                    "event_code": booking.event_code,
                    "payment_id": booking.payment_id,
                    "event_id": booking.event_id,
                    "contract_id": contract.id,
                    "contract_number": contract.contract_number,
                    "contract_status": contract.status,
                    "quote_status": booking.quote_status,
                    "services_subtotal": booking.total_amount - booking.mobility_amount,
                    "total_amount": booking.total_amount,
                    "advance_amount": booking.advance_amount,
                    "pending_balance": booking.total_amount - booking.advance_amount,
                }
            ),
            status_code=201 if created else 200,
        )
    except InvalidAdvanceAmount as exc:
        raise ProblemError(400, exc.code, "Adelanto inválido", str(exc)) from exc
    except DomainError as exc:
        raise problem(exc) from exc
