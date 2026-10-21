from uuid import UUID

from sqlalchemy import text

from app.application.dtos.manual_contract_dto import ManualContractInput
from app.infrastructure.adapters.secondary.persistence.manual_booking_repository import (
    SqlAlchemyManualBookingStore,
)


class SqlAlchemyManualContractStore(SqlAlchemyManualBookingStore):
    async def set_details(self, request: ManualContractInput) -> None:
        await self._session.execute(
            text(
                "UPDATE clients SET full_name=:name,dni=:dni,ruc=:ruc "
                "WHERE id=(SELECT client_id FROM quotes WHERE id=:quote)"
            ),
            {
                "name": request.budget.client_name,
                "dni": request.dni,
                "ruc": request.ruc,
                "quote": request.quote_id,
            },
        )
        for extra_id, quantity in request.quantities:
            await self._session.execute(
                text(
                    "UPDATE quote_extras SET quantity=:qty,unit_price=subtotal/:qty "
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
