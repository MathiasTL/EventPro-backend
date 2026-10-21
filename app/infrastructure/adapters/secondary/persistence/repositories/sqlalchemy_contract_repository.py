"""Persistencia de contratos, bloqueada por evento y sin commits internos."""

from dataclasses import fields
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.contract_dto import ContractData, ContractFilters, ContractPage
from app.domain.entities.audit_log import AuditLog
from app.domain.entities.contract import Contract, ContractStatus
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError
from app.infrastructure.adapters.secondary.persistence.models.audit_log import (
    AuditLog as AuditModel,
)
from app.infrastructure.adapters.secondary.persistence.models.catalog_models import (
    ExtraModel,
    PackageModel,
    ThemeModel,
)
from app.infrastructure.adapters.secondary.persistence.models.client_model import ClientModel
from app.infrastructure.adapters.secondary.persistence.models.contract_model import ContractModel
from app.infrastructure.adapters.secondary.persistence.models.event_model import EventModel
from app.infrastructure.adapters.secondary.persistence.models.outbox_message_model import (
    OutboxMessageModel,
)
from app.infrastructure.adapters.secondary.persistence.models.payment_model import PaymentModel
from app.infrastructure.adapters.secondary.persistence.models.quote_model import (
    QuoteExtraModel,
    QuoteModel,
)


def to_contract(model: ContractModel) -> Contract:
    values = {field.name: getattr(model, field.name) for field in fields(Contract)}
    values["status"] = ContractStatus(model.status)
    return Contract(**values)


class SqlAlchemyContractRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_token(self, token_hash: str) -> Contract | None:
        row = await self._session.scalar(
            select(ContractModel)
            .where(ContractModel.signature_token_hash == token_hash)
            .execution_options(populate_existing=True)
        )
        return to_contract(row) if row else None

    async def schedule_event(self, event_id: UUID) -> None:
        await self._session.execute(
            update(EventModel).where(EventModel.id == event_id).values(status="SCHEDULED")
        )

    async def get(self, contract_id: UUID) -> Contract | None:
        model = await self._session.scalar(
            select(ContractModel)
            .where(ContractModel.id == contract_id)
            .execution_options(populate_existing=True)
        )
        return to_contract(model) if model else None

    async def active_for_event(self, event_id: UUID) -> Contract | None:
        row = await self._session.scalar(
            select(ContractModel)
            .where(ContractModel.event_id == event_id, ContractModel.status != "VOIDED")
            .execution_options(populate_existing=True)
        )
        return to_contract(row) if row else None

    async def event_data(self, event_id: UUID, *, lock: bool = False) -> ContractData:
        query = select(EventModel).where(EventModel.id == event_id)
        if lock:
            query = query.with_for_update()
        event = await self._session.scalar(query.execution_options(populate_existing=True))
        if event is None:
            raise ResourceNotFoundError("Evento no encontrado")
        row = (
            await self._session.execute(
                select(QuoteModel, ClientModel, PackageModel.name, ThemeModel.name)
                .join(ClientModel, ClientModel.id == QuoteModel.client_id)
                .join(PackageModel, PackageModel.id == QuoteModel.package_id)
                .outerjoin(ThemeModel, ThemeModel.id == QuoteModel.theme_id)
                .where(QuoteModel.id == event.quote_id)
            )
        ).one()
        quote, client, package_name, theme_name = row
        extra_rows = (
            await self._session.execute(
                select(ExtraModel.name, QuoteExtraModel.quantity, QuoteExtraModel.subtotal)
                .join(ExtraModel, ExtraModel.id == QuoteExtraModel.extra_id)
                .where(QuoteExtraModel.quote_id == quote.id)
                .order_by(ExtraModel.name)
            )
        ).all()
        paid = await self._session.scalar(
            select(func.coalesce(func.sum(PaymentModel.amount), 0)).where(
                PaymentModel.event_id == event_id,
                PaymentModel.quote_id == quote.id,
                PaymentModel.concept == "ADVANCE",
                PaymentModel.validation_status == "VERIFIED",
            )
        )
        return ContractData(
            event_id=event.id,
            event_status=event.status,
            quote_id=quote.id,
            source=quote.source,
            client_name=client.full_name,
            phone=client.phone,
            dni=client.dni,
            ruc=client.ruc,
            event_date=event.event_date,
            start_time=event.start_time,
            end_time=event.end_time,
            address=event.address,
            district=event.district,
            package_name=package_name,
            theme_name=theme_name,
            extras=tuple(f"{name} x {qty}: S/ {amount:.2f}" for name, qty, amount in extra_rows),
            services=event.total_services_amount,
            mobility=event.total_mobility_amount,
            total=event.final_total_amount,
            advance=Decimal(paid or 0),
            required_advance=quote.advance_amount,
            observations=event.client_observations,
            event_started=event.actual_start_time is not None,
        )

    async def next_number(self, year: int) -> str:
        value = await self._session.scalar(text("SELECT nextval('contract_number_seq')"))
        return f"CTR-{year}-{int(value):04d}"

    async def save(self, contract: Contract) -> None:
        model = await self._session.get(ContractModel, contract.id)
        if model is None:
            model = ContractModel()
            self._session.add(model)
        for field in fields(Contract):
            value = getattr(contract, field.name)
            setattr(model, field.name, value.value if isinstance(value, ContractStatus) else value)
        await self._session.flush()

    async def list(self, filters: ContractFilters) -> ContractPage:
        clauses = []
        if filters.status is not None:
            clauses.append(ContractModel.status == filters.status.value)
        if filters.event_id is not None:
            clauses.append(ContractModel.event_id == filters.event_id)
        if filters.is_manual_mode is not None:
            clauses.append(ContractModel.is_manual_mode == filters.is_manual_mode)
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(ContractModel).where(*clauses)
            )
            or 0
        )
        rows = await self._session.scalars(
            select(ContractModel)
            .where(*clauses)
            .order_by(ContractModel.created_at.desc(), ContractModel.id.desc())
            .offset((filters.page - 1) * filters.page_size)
            .limit(filters.page_size)
        )
        return ContractPage(
            [to_contract(row) for row in rows], filters.page, filters.page_size, total
        )

    async def set_observations(self, event_id: UUID, text: str | None) -> None:
        await self._session.execute(
            update(EventModel).where(EventModel.id == event_id).values(client_observations=text)
        )

    async def record_audit(self, entry: AuditLog) -> None:
        self._session.add(AuditModel(**{f.name: getattr(entry, f.name) for f in fields(AuditLog)}))
        await self._session.flush()

    async def invalidate_pending_links(self, contract_id: UUID) -> None:
        await self._session.execute(
            update(OutboxMessageModel)
            .where(
                OutboxMessageModel.status == "PENDING",
                OutboxMessageModel.payload["contract_id"].astext == str(contract_id),
            )
            .values(status="FAILED", payload=None, last_error="Enlace reemplazado o anulado")
        )
