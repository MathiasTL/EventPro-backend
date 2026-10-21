from uuid import UUID

from sqlalchemy import select, text

from app.application.dtos.manual_contract_dto import ManualContractInput
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError
from app.infrastructure.adapters.secondary.persistence.manual_booking_repository import (
    SqlAlchemyManualBookingStore,
)
from app.infrastructure.adapters.secondary.persistence.models.audit_log import AuditLog
from app.infrastructure.adapters.secondary.persistence.models.client_model import ClientModel


class SqlAlchemyManualContractStore(SqlAlchemyManualBookingStore):
    async def get_identity(self, quote_id: UUID) -> tuple[str, str | None, str | None]:
        row = (
            await self._session.execute(
                text(
                    "SELECT c.full_name,c.dni,c.ruc FROM clients c "
                    "JOIN quotes q ON q.client_id=c.id WHERE q.id=:quote"
                ),
                {"quote": quote_id},
            )
        ).one()
        return row.full_name, row.dni, row.ruc

    async def set_details(self, request: ManualContractInput, user_id: UUID) -> None:
        client_id = await self._session.scalar(
            text("SELECT client_id FROM quotes WHERE id=:quote"), {"quote": request.quote_id}
        )
        client = await self._session.scalar(
            select(ClientModel)
            .where(ClientModel.id == client_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if client is None:
            raise ResourceNotFoundError("Cliente de la cotización no encontrado")
        supplied = {"full_name": request.budget.client_name, "dni": request.dni, "ruc": request.ruc}
        old_values: dict[str, object] = {}
        new_values: dict[str, object] = {}
        for field, value in supplied.items():
            if field in request.identity_fields and getattr(client, field) != value:
                old_values[field] = getattr(client, field)
                new_values[field] = value
                setattr(client, field, value)
        if new_values:
            self._session.add(
                AuditLog(
                    user_id=user_id,
                    action="MANUAL_CONTRACT",
                    entity_name="clients",
                    entity_id=client.id,
                    old_values=old_values,
                    new_values={**new_values, "quote_id": str(request.quote_id)},
                )
            )
        await self._session.flush()
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
        # La conversión del agregado puede haber usado su instantánea anterior de notas.
        await self._session.execute(
            text("UPDATE quotes SET observations=:notes WHERE id=:id"),
            {"notes": request.observations, "id": request.quote_id},
        )
        await self._session.execute(
            text("UPDATE events SET client_observations=:notes WHERE id=:id"),
            {"notes": request.observations, "id": event_id},
        )
        await self._session.execute(
            text("UPDATE contracts SET custom_clauses=:clauses WHERE id=:id"),
            {"clauses": request.clauses, "id": contract_id},
        )
