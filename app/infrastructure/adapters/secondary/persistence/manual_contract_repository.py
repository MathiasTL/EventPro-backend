from uuid import UUID

from sqlalchemy import text, update

from app.application.dtos.manual_contract_dto import ManualContractInput
from app.infrastructure.adapters.secondary.persistence.manual_booking_repository import (
    SqlAlchemyManualBookingStore,
)
from app.infrastructure.adapters.secondary.persistence.models.client_model import ClientModel


class SqlAlchemyManualContractStore(SqlAlchemyManualBookingStore):
    async def set_details(self, request: ManualContractInput) -> None:
        client_id = await self._session.scalar(
            text("SELECT client_id FROM quotes WHERE id=:quote"), {"quote": request.quote_id}
        )
        await self._session.execute(
            update(ClientModel)
            .where(ClientModel.id == client_id)
            .values(
                full_name=request.budget.client_name,
                dni=request.dni,
                ruc=request.ruc,
            )
        )
        await self._session.execute(
            text("UPDATE quotes SET observations=:notes WHERE id=:quote"),
            {"notes": request.observations, "quote": request.quote_id},
        )
        for extra_id, quantity in request.quantities:
            await self._session.execute(
                text(
                    "UPDATE quote_extras SET quantity=CAST(:qty AS integer), "
                    "unit_price=subtotal/CAST(:qty AS integer) "
                    "WHERE quote_id=:quote AND extra_id=:extra"
                ),
                {"qty": quantity, "quote": request.quote_id, "extra": extra_id},
            )
        await self._session.execute(
            text(
                "UPDATE payments SET transaction_reference=:reference "
                "WHERE quote_id=:quote AND concept='ADVANCE'"
            ),
            {"reference": request.reference, "quote": request.quote_id},
        )

    async def set_contract_details(
        self, event_id: UUID, contract_id: UUID, request: ManualContractInput
    ) -> None:
        await self._session.execute(
            text("UPDATE events SET client_observations=:notes WHERE id=:id"),
            {"notes": request.observations, "id": event_id},
        )
        await self._session.execute(
            text("UPDATE contracts SET custom_clauses=:clauses WHERE id=:id"),
            {"clauses": request.clauses, "id": contract_id},
        )
