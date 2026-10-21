"""Contrato REST administrativo. Nunca expone hashes, rutas privadas ni OTP."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.entities.contract import ContractStatus


class ContractRead(BaseModel):
    contract_id: UUID
    contract_number: str
    event_id: UUID
    status: ContractStatus
    is_manual_mode: bool
    custom_clauses: str | None = None
    signature_token_expires_at: datetime | None = None
    signed_at: datetime | None = None
    signer_ip: str | None = None
    sealed_pdf_sha256: str | None = None
    is_timestamped: bool = False
    created_at: datetime


class ContractPageResponse(BaseModel):
    items: list[ContractRead]
    page: int
    page_size: int
    total: int


class IssueContractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: UUID = Field(description="Evento con adelanto ya verificado")


class VoidContractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=1000)


class ContractObservationsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_observations: str | None = Field(max_length=5000)
