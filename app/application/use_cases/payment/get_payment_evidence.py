"""Sirve la evidencia de pago previamente almacenada."""

from uuid import UUID

from app.application.ports.output.payment_evidence_storage_port import IPaymentEvidenceStoragePort
from app.application.ports.output.payment_repository_port import IPaymentRepositoryPort
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError


class GetPaymentEvidenceUseCase:
    def __init__(
        self, payments: IPaymentRepositoryPort, evidence: IPaymentEvidenceStoragePort
    ) -> None:
        self._payments = payments
        self._evidence = evidence

    async def execute(self, payment_id: UUID) -> bytes:
        payment = await self._payments.get_by_id(payment_id)
        if payment is None:
            raise ResourceNotFoundError("Pago no encontrado")
        return await self._evidence.open(payment.evidence_path)
