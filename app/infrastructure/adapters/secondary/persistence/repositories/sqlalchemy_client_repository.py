"""Repositorio de clientes con SQLAlchemy. No confirma: la transacción es del llamador."""

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.client import Client
from app.domain.value_objects.phone_number import PhoneNumber
from app.infrastructure.adapters.secondary.persistence.mappers.client_mapper import (
    client_to_domain,
)
from app.infrastructure.adapters.secondary.persistence.models.client_model import ClientModel


class SqlAlchemyClientRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, client_id: UUID) -> Client | None:
        row = await self._session.get(ClientModel, client_id)
        return client_to_domain(row) if row is not None else None

    async def get_by_phone(self, phone: str) -> Client | None:
        row = await self._find_row(PhoneNumber.parse(phone))
        return client_to_domain(row) if row is not None else None

    async def get_or_create(self, phone: str, full_name: str) -> Client:
        number = PhoneNumber.parse(phone)
        existing = await self._find_row(number)
        if existing is not None:
            return client_to_domain(existing)
        candidate = Client(phone=number, full_name=full_name)
        await self._session.execute(
            pg_insert(ClientModel)
            .values(
                id=uuid4(),
                phone=candidate.phone.value,
                full_name=candidate.full_name,
                created_at=candidate.created_at,
            )
            .on_conflict_do_nothing(index_elements=["phone"])
        )
        row = await self._find_row(number)
        if row is None:  # pragma: no cover - ON CONFLICT garantiza que la fila existe
            raise RuntimeError("El cliente no existe tras el upsert")
        return client_to_domain(row)

    async def _find_row(self, number: PhoneNumber) -> ClientModel | None:
        """Busca el formato canónico y los heredados (``51…`` y local), el canónico primero."""

        stmt = (
            select(ClientModel)
            .where(ClientModel.phone.in_({number.value, number.digits, number.national}))
            .order_by((ClientModel.phone == number.value).desc())
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()
