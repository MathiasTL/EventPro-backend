"""API pública de firma; la credencial es el token, sin JWT de personal."""

import base64
import binascii
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.application.use_cases.contract.sign_contract import SignatureError, SignContract
from app.infrastructure.adapters.primary.web.problem import ProblemError, problem_response
from app.infrastructure.adapters.primary.web.rate_limit import limiter
from app.infrastructure.adapters.secondary.persistence.database import get_contract_write_session
from app.infrastructure.adapters.secondary.signature.pades_signature_adapter import (
    validate_signature_image,
)
from app.infrastructure.di.containers import get_sign_contract_use_case

router = APIRouter(prefix="/contracts/sign", tags=["Firma electrónica"])
UseCase = Annotated[SignContract, Depends(get_sign_contract_use_case)]
Transaction = Annotated[AsyncSession, Depends(get_contract_write_session, scope="function")]


class OtpRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    otp_code: str = Field(pattern=r"^[0-9]{6}$")


class SignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    otp_proof: str = Field(min_length=20, max_length=2048)
    signature_base64: str = Field(max_length=1_400_000)
    signer_full_name: str = Field(min_length=2, max_length=120, pattern=r"^[^\x00-\x1f\x7f]+$")
    accept_terms: bool = Field(strict=True)

    @field_validator("accept_terms")
    @classmethod
    def require_acceptance(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Acepta los términos antes de firmar")
        return value


def error(exc: SignatureError) -> ProblemError:
    return ProblemError(exc.status, exc.code, "Firma no disponible", str(exc))


@router.get("/{token}")
@limiter.shared_limit("30/minute", scope="signature-read")
async def view_contract(request: Request, token: str, use_case: UseCase) -> JSONResponse:
    try:
        contract, data = await use_case.resolve(token)
        return JSONResponse(
            jsonable_encoder(
                {
                    "contract_number": contract.contract_number,
                    "status": contract.status,
                    "client_full_name": data.client_name,
                    "event": {
                        "event_date": data.event_date,
                        "start_time": data.start_time,
                        "end_time": data.end_time,
                        "address": data.address,
                        "district": data.district,
                        "package_name": data.package_name,
                        "theme_name": data.theme_name,
                        "client_observations": data.observations,
                    },
                    "total_amount": data.total,
                    "advance_paid": data.advance,
                    "pending_balance": data.total - data.advance,
                    "pdf_url": f"{request.url.path}/pdf",
                    "token_expires_at": contract.signature_token_expires_at,
                }
            )
        )
    except SignatureError as exc:
        raise error(exc) from exc


@router.get("/{token}/pdf")
@limiter.shared_limit("30/minute", scope="signature-read")
async def public_pdf(request: Request, token: str, use_case: UseCase) -> Response:
    try:
        return Response(
            await use_case.pdf(token),
            media_type="application/pdf",
            headers={"Content-Disposition": 'inline; filename="contrato.pdf"'},
        )
    except SignatureError as exc:
        raise error(exc) from exc


@router.post("/{token}/otp")
@limiter.shared_limit("10/hour", scope="signature-otp-request")
async def request_otp(
    request: Request,
    token: str,
    transaction: Transaction,
    use_case: UseCase,
) -> JSONResponse:
    try:
        return JSONResponse(await use_case.request_otp(token))
    except SignatureError as exc:
        raise error(exc) from exc


@router.post("/{token}/otp/verify")
@limiter.shared_limit("20/hour", scope="signature-otp-verify")
async def verify_otp(
    request: Request,
    token: str,
    payload: OtpRequest,
    transaction: Transaction,
    use_case: UseCase,
) -> JSONResponse:
    try:
        result = await use_case.verify_otp(token, payload.otp_code)
        if isinstance(result, SignatureError):
            # Retornar, no lanzar: así se confirma el contador de intentos fallidos.
            return problem_response(
                request, result.status, result.code, "OTP no válido", str(result)
            )
        return JSONResponse(result)
    except SignatureError as exc:
        raise error(exc) from exc


@router.post("/{token}")
@limiter.shared_limit("10/hour", scope="signature-submit")
async def sign_contract(
    request: Request,
    token: str,
    payload: SignRequest,
    transaction: Transaction,
    use_case: UseCase,
) -> JSONResponse:
    try:
        encoded = payload.signature_base64
        if encoded.startswith("data:image/png;base64,"):
            encoded = encoded.removeprefix("data:image/png;base64,")
        try:
            image = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise SignatureError(422, "validation-error", "Firma PNG inválida") from exc
        await run_in_threadpool(validate_signature_image, image)
        contract = await use_case.sign(
            token,
            payload.otp_proof,
            image,
            payload.signer_full_name,
            ip=request.client.host if request.client else "0.0.0.0",
            user_agent=request.headers.get("user-agent", ""),
        )
        return JSONResponse(
            jsonable_encoder(
                {
                    "contract_number": contract.contract_number,
                    "status": contract.status,
                    "signed_at": contract.signed_at,
                    "sealed_pdf_sha256": contract.sealed_pdf_sha256,
                    "message": "Contrato firmado. Se ha encolado una copia para tu WhatsApp.",
                }
            )
        )
    except SignatureError as exc:
        raise error(exc) from exc
