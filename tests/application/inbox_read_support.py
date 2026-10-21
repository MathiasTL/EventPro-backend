"""Dobles de la lectura de la bandeja: consultas por lote que cuentan sus llamadas."""

from collections.abc import Collection, Mapping
from uuid import UUID

from app.domain.entities.quote import QuoteStatus


class FakeInboxLookup:
    """``IInboxLookupPort`` en memoria; ``calls`` permite comprobar que no hay N+1."""

    def __init__(
        self,
        *,
        clients: Mapping[UUID, str] | None = None,
        users: Mapping[UUID, str] | None = None,
        quotes: Mapping[UUID, QuoteStatus] | None = None,
        settled: Collection[UUID] = (),
    ) -> None:
        self.clients = dict(clients or {})
        self.users = dict(users or {})
        self.quotes = dict(quotes or {})
        self.settled = set(settled)
        self.calls: list[str] = []
        self.error: Exception | None = None

    async def client_names(self, client_ids: Collection[UUID]) -> Mapping[UUID, str]:
        return self._answer("client_names", self.clients, client_ids)

    async def user_names(self, user_ids: Collection[UUID]) -> Mapping[UUID, str]:
        return self._answer("user_names", self.users, user_ids)

    async def quote_statuses(self, quote_ids: Collection[UUID]) -> Mapping[UUID, QuoteStatus]:
        return self._answer("quote_statuses", self.quotes, quote_ids)

    async def settled_quote_ids(self, quote_ids: Collection[UUID]) -> set[UUID]:
        self.calls.append("settled_quote_ids")
        if self.error is not None:
            raise self.error
        return self.settled.intersection(quote_ids)

    def _answer[V](
        self, name: str, source: Mapping[UUID, V], ids: Collection[UUID]
    ) -> dict[UUID, V]:
        self.calls.append(name)
        if self.error is not None:
            raise self.error
        return {key: source[key] for key in ids if key in source}
