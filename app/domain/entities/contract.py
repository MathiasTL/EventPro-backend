"""Contrato: estados e invariantes, sin dependencias de infraestructura."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain.exceptions.resource_exceptions import ResourceInUseError, ValidationError


class InvalidContractStateError(ResourceInUseError):
    code = "invalid-contract-state"


class ContractStatus(StrEnum):
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    SIGNED = "SIGNED"
    VOIDED = "VOIDED"


@dataclass(kw_only=True)
class Contract:
    contract_number: str
    event_id: UUID
    id: UUID = field(default_factory=uuid4)
    status: ContractStatus = ContractStatus.DRAFT
    pdf_storage_path: str | None = None
    is_manual_mode: bool = False
    custom_clauses: str | None = None
    signature_token_hash: str | None = None
    signature_token_expires_at: datetime | None = None
    otp_hash: str | None = None
    otp_expires_at: datetime | None = None
    otp_attempts: int = 0
    otp_last_requested_at: datetime | None = None
    otp_window_started_at: datetime | None = None
    otp_request_count: int = 0
    signature_image_path: str | None = None
    signer_ip: str | None = None
    signer_user_agent: str | None = None
    signed_at: datetime | None = None
    sealed_pdf_storage_path: str | None = None
    sealed_pdf_sha256: str | None = None
    is_timestamped: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not isinstance(self.status, ContractStatus):
            raise ValidationError("Estado de contrato inválido")
        if not self.contract_number.strip() or len(self.contract_number) > 30:
            raise ValidationError("Correlativo de contrato inválido")
        if self.otp_attempts < 0:
            raise ValidationError("otp_attempts no puede ser negativo")
        if (
            self.status in (ContractStatus.ISSUED, ContractStatus.SIGNED)
            and not self.pdf_storage_path
        ):
            raise ValidationError("Un contrato emitido requiere PDF")
        if self.status is ContractStatus.SIGNED and not (
            self.signed_at and self.sealed_pdf_storage_path and self.sealed_pdf_sha256
        ):
            raise ValidationError("Un contrato firmado requiere evidencia del sello")

    def require_editable(self) -> None:
        if self.status not in (ContractStatus.DRAFT, ContractStatus.ISSUED):
            raise InvalidContractStateError("El contrato firmado o anulado no admite cambios")

    def issue(self, path: str) -> None:
        self.require_editable()
        if not path:
            raise ValidationError("El PDF es obligatorio")
        self.pdf_storage_path = path
        self.status = ContractStatus.ISSUED

    def replace_link(self, token_hash: str, expires_at: datetime) -> None:
        if self.status is not ContractStatus.ISSUED:
            raise InvalidContractStateError("Solo un contrato emitido admite enlace")
        if expires_at.tzinfo is None:
            raise ValidationError("La expiración requiere zona horaria")
        self.signature_token_hash = token_hash
        self.signature_token_expires_at = expires_at
        self.otp_hash = None
        self.otp_expires_at = None
        self.otp_attempts = 0

    def void(self, *, event_status: str, reason: str, event_started: bool = False) -> None:
        if not reason.strip():
            raise ValidationError("La anulación requiere un motivo")
        if self.status is ContractStatus.VOIDED:
            raise InvalidContractStateError("El contrato ya está anulado")
        if self.status is ContractStatus.SIGNED and event_status != "CANCELLED":
            raise InvalidContractStateError("Un contrato firmado exige cancelar el evento")
        if event_started or event_status in ("IN_PROGRESS", "EXTENDED", "SETTLED"):
            raise InvalidContractStateError("No se puede anular durante o después del evento")
        self.status = ContractStatus.VOIDED
        self.signature_token_hash = None
        self.signature_token_expires_at = None
        self.otp_hash = None
        self.otp_expires_at = None
        self.otp_attempts = 0
