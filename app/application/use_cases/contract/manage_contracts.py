"""RF-13: emisión idempotente, consulta, regeneración, reenvío y anulación."""

import hashlib
import secrets
from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

from app.application.dtos.contract_dto import ContractData, ContractFilters, ContractPage
from app.application.ports.output.clock_port import IClockPort
from app.application.ports.output.contract_port import IContractPdf, IContractRepository
from app.application.ports.output.manual_booking_port import IBookingDocuments
from app.application.use_cases.messaging.enqueue_message import EnqueueMessage
from app.domain.entities.audit_log import AuditLog
from app.domain.entities.contract import Contract, ContractStatus, InvalidContractStateError
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError, ValidationError
from app.domain.value_objects.outbox import MessageType
from app.domain.value_objects.phone_number import PhoneNumber


class ManageContracts:
    def __init__(
        self,
        repository: IContractRepository,
        documents: IBookingDocuments,
        pdf: IContractPdf,
        messages: EnqueueMessage,
        clock: IClockPort,
        *,
        frontend_url: str,
        link_ttl_hours: int = 168,
    ) -> None:
        self._repo = repository
        self._documents = documents
        self._pdf = pdf
        self._messages = messages
        self._clock = clock
        self._frontend_url = frontend_url.rstrip("/")
        self._ttl = timedelta(hours=link_ttl_hours)

    async def get(self, contract_id: UUID) -> Contract:
        contract = await self._repo.get(contract_id)
        if contract is None:
            raise ResourceNotFoundError("Contrato no encontrado")
        return contract

    async def list(self, filters: ContractFilters) -> ContractPage:
        if filters.page < 1 or not 1 <= filters.page_size <= 100:
            raise ValidationError("Paginación inválida")
        return await self._repo.list(filters)

    async def prepare_manual_pdf(self, contract: Contract, data: ContractData) -> None:
        """Prepara el documento transaccional antes del candado global; no publica el enlace."""
        if not contract.is_manual_mode or contract.event_id != data.event_id:
            raise ValidationError("La vista previa no corresponde al contrato manual")
        await self._render(contract, data)

    async def _locked(self, contract_id: UUID) -> tuple[Contract, ContractData]:
        previous = await self.get(contract_id)
        data = await self._repo.event_data(previous.event_id, lock=True)
        # Releer tras esperar el candado del evento: evita usar un estado obsoleto.
        return await self.get(contract_id), data

    @staticmethod
    def _require_paid(data: ContractData) -> None:
        if data.services + data.mobility != data.total or data.advance > data.total:
            raise InvalidContractStateError(
                "Los importes del evento y del adelanto no son coherentes"
            )
        if data.advance < data.required_advance or data.advance <= 0:
            raise InvalidContractStateError("Se requiere un adelanto verificado para emitir")
        if data.event_status != "AWAITING_SIGNATURE":
            raise InvalidContractStateError("El evento no admite emisión de contrato")

    async def prepare_payment_event(self, event_id: UUID, quote_id: UUID) -> None:
        data = await self._repo.event_data(event_id, lock=True)
        if data.quote_id != quote_id:
            raise ValidationError("El evento no pertenece a la cotización del pago")
        if data.event_status != "AWAITING_SIGNATURE":
            raise InvalidContractStateError("El evento no está pendiente de contrato")

    async def issue_for_event(self, event_id: UUID, user_id: UUID | None = None) -> Contract:
        data = await self._repo.event_data(event_id, lock=True)
        self._require_paid(data)
        contract = await self._repo.active_for_event(event_id)
        if contract is not None and (
            contract.status is ContractStatus.SIGNED
            or (contract.status is ContractStatus.ISSUED and contract.signature_token_hash)
        ):
            return contract
        if contract is None:
            contract = Contract(
                contract_number=await self._repo.next_number(self._clock.utcnow().year),
                event_id=event_id,
                is_manual_mode=data.source == "MANUAL",
                created_at=self._clock.utcnow(),
            )
        # El flujo manual ya renderizó su documento antes del candado de disponibilidad.
        # Adoptarlo evita duplicar el PDF y mantiene la sección crítica corta.
        if contract.status is not ContractStatus.ISSUED or not contract.pdf_storage_path:
            await self._render(contract, data)
        await self._link(contract, data)
        await self._repo.save(contract)
        await self._audit(contract, "CONTRACT_ISSUED", user_id)
        return contract

    async def _render(self, contract: Contract, data: ContractData) -> None:
        content = await self._pdf.render(contract, data)
        path = await self._documents.store(
            data=content,
            content_type="application/pdf",
            original_filename=f"{contract.contract_number}.pdf",
        )
        contract.issue(path)

    async def _link(self, contract: Contract, data: ContractData) -> None:
        token = secrets.token_urlsafe(32)
        contract.replace_link(
            hashlib.sha256(token.encode()).hexdigest(), self._clock.utcnow() + self._ttl
        )
        await self._repo.invalidate_pending_links(contract.id)
        # El token en claro solo persiste en la cola hasta que el gateway acepta el envío.
        await self._messages.execute(
            recipient=PhoneNumber.parse(data.phone),
            message_type=MessageType.TEXT,
            payload={
                "contract_id": str(contract.id),
                "body": f"Revisa tu contrato {contract.contract_number}: "
                f"{self._frontend_url}/contracts/sign/{token}",
            },
            redact_after_send=True,
        )

    async def resend(self, contract_id: UUID, user_id: UUID) -> Contract:
        contract, data = await self._locked(contract_id)
        self._require_paid(data)
        await self._link(contract, data)
        await self._repo.save(contract)
        await self._audit(contract, "CONTRACT_LINK_RESENT", user_id)
        return contract

    async def update_observations(
        self, contract_id: UUID, observations: str | None, user_id: UUID
    ) -> Contract:
        contract, data = await self._locked(contract_id)
        contract.require_editable()
        self._require_paid(data)
        if observations is not None and len(observations) > 5000:
            raise ValidationError("Las observaciones admiten hasta 5000 caracteres")
        if data.observations == observations:
            return contract
        await self._repo.set_observations(contract.event_id, observations)
        was_draft = contract.status is ContractStatus.DRAFT
        await self._render(contract, replace(data, observations=observations))
        if was_draft:
            contract.status = ContractStatus.DRAFT
        else:
            await self._link(contract, data)
        await self._repo.save(contract)
        await self._audit(
            contract,
            "CONTRACT_REGENERATED",
            user_id,
            old_values={"client_observations": data.observations},
            new_values={"client_observations": observations},
        )
        return contract

    async def void(self, contract_id: UUID, reason: str, user_id: UUID) -> Contract:
        contract, data = await self._locked(contract_id)
        previous = contract.status.value
        contract.void(
            event_status=data.event_status, reason=reason, event_started=data.event_started
        )
        await self._repo.invalidate_pending_links(contract.id)
        await self._repo.save(contract)
        await self._audit(
            contract,
            "CONTRACT_VOIDED",
            user_id,
            old_values={"status": previous},
            new_values={"reason": reason},
        )
        return contract

    async def pdf(self, contract_id: UUID) -> bytes:
        contract = await self.get(contract_id)
        if contract.status is ContractStatus.DRAFT:
            raise ResourceNotFoundError("El contrato todavía no está emitido")
        path = (
            contract.sealed_pdf_storage_path
            if contract.signed_at is not None
            else contract.pdf_storage_path
        )
        if not path:
            raise ResourceNotFoundError("El contrato todavía no tiene PDF")
        return await self._documents.open(path)

    async def _audit(
        self,
        contract: Contract,
        action: str,
        user_id: UUID | None,
        *,
        old_values: dict[str, object] | None = None,
        new_values: dict[str, object] | None = None,
    ) -> None:
        await self._repo.record_audit(
            AuditLog(
                id=uuid4(),
                action=action,
                entity_name="contracts",
                entity_id=contract.id,
                user_id=user_id,
                old_values=old_values,
                new_values={"status": contract.status.value, **(new_values or {})},
            )
        )
