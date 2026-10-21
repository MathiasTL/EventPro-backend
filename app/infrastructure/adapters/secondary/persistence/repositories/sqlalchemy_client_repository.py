"""Repositorio de clientes con SQLAlchemy. No confirma: la transacción es del llamador."""

from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.client_dto import (
    ClientDetailDTO,
    ClientDTO,
    ClientQuoteSummaryDTO,
    FindClientsFilter,
)
from app.application.dtos.page_dto import PageDTO
from app.domain.entities.client import Client
from app.domain.entities.quote import QuoteStatus
from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.phone_number import PhoneNumber
from app.infrastructure.adapters.secondary.persistence.mappers.client_mapper import (
    client_to_domain,
)
from app.infrastructure.adapters.secondary.persistence.models.client_model import ClientModel
from app.infrastructure.adapters.secondary.persistence.models.quote_model import QuoteModel


class SqlAlchemyClientRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, client_id: UUID) -> Client | None:
        row = await self._session.get(ClientModel, client_id)
        return client_to_domain(row) if row is not None else None

    async def find(self, filters: FindClientsFilter) -> PageDTO[ClientDTO]:
        query = select(ClientModel)
        if filters.phone:
            number = PhoneNumber.parse(filters.phone)
            query = query.where(
                ClientModel.phone.in_({number.value, number.digits, number.national})
            )
        needle = (filters.q or "").strip()
        if needle:
            digits = "".join(char for char in needle if char.isdigit())
            try:
                number = PhoneNumber.parse(needle)
                digits = number.national if number.value.startswith("+51") else number.digits
            except ValidationError:
                pass  # Una búsqueda libre puede ser un nombre o un fragmento de teléfono.
            name_match = ClientModel.full_name.icontains(needle, autoescape=True)
            if digits:
                # El teléfono es una cadena de dígitos; '%' y '_' nunca son comodines aquí.
                query = query.where(
                    or_(name_match, ClientModel.phone.contains(digits, autoescape=True))
                )
            else:
                query = query.where(name_match)
        total = await self._session.scalar(select(func.count()).select_from(query.subquery()))
        rows = await self._session.scalars(
            query.order_by(ClientModel.created_at.desc(), ClientModel.id.desc())
            .offset((filters.page - 1) * filters.page_size)
            .limit(filters.page_size)
        )
        return PageDTO(
            items=tuple(self._to_dto(row) for row in rows),
            page=filters.page,
            page_size=filters.page_size,
            total=total or 0,
        )

    @staticmethod
    def _to_dto(row: ClientModel) -> ClientDTO:
        # La columna no restringe el formato: un registro no normalizable se muestra tal cual
        # en lugar de impedir el listado completo.
        try:
            phone = PhoneNumber.parse(row.phone).value
        except ValidationError:
            phone = row.phone
        return ClientDTO(
            id=row.id,
            phone=phone,
            full_name=row.full_name,
            dni=row.dni,
            ruc=row.ruc,
            created_at=row.created_at,
        )

    async def get_detail(self, client_id: UUID) -> ClientDetailDTO | None:
        row = await self._session.get(ClientModel, client_id)
        if row is None:
            return None
        client = self._to_dto(row)
        quotes = await self._session.scalars(
            select(QuoteModel)
            .where(QuoteModel.client_id == client_id)
            .order_by(QuoteModel.event_date.desc(), QuoteModel.id.desc())
        )
        return ClientDetailDTO(
            id=client.id,
            phone=client.phone,
            full_name=client.full_name,
            dni=client.dni,
            ruc=client.ruc,
            created_at=client.created_at,
            quotes=tuple(
                ClientQuoteSummaryDTO(
                    quote.id, quote.event_date, quote.total_amount, QuoteStatus(quote.status)
                )
                for quote in quotes
            ),
        )

    async def get_by_phone(self, phone: str) -> Client | None:
        row = await self._find_row(PhoneNumber.parse(phone))
        return client_to_domain(row) if row is not None else None

    async def get_or_create(
        self, phone: str, full_name: str, *, dni: str | None = None, ruc: str | None = None
    ) -> Client:
        number = PhoneNumber.parse(phone)
        existing = await self._find_row(number)
        if existing is not None:
            return client_to_domain(existing)
        candidate = Client(phone=number, full_name=full_name, dni=dni, ruc=ruc)
        await self._session.execute(
            pg_insert(ClientModel)
            .values(
                id=uuid4(),
                phone=candidate.phone.value,
                full_name=candidate.full_name,
                dni=candidate.dni,
                ruc=candidate.ruc,
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
