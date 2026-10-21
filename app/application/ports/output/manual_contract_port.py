from typing import Protocol
from uuid import UUID

from app.application.dtos.manual_contract_dto import ManualContractInput
from app.application.ports.output.manual_booking_port import IManualBookingStore


class IManualContractStore(IManualBookingStore, Protocol):
    async def set_details(self, request: ManualContractInput, user_id: UUID) -> None: ...
    async def get_identity(self, quote_id: UUID) -> tuple[str, str | None, str | None]: ...
    async def set_contract_details(
        self, event_id: UUID, contract_id: UUID, request: ManualContractInput
    ) -> None: ...
