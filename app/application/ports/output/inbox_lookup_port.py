from collections.abc import Collection, Mapping
from typing import Protocol
from uuid import UUID

from app.domain.entities.quote import QuoteStatus


class IInboxLookupPort(Protocol):
    """Consultas de solo lectura por lote para armar la bandeja (spec 09, 5.4).

    Un puerto aparte evita tocar los repositorios de cotizaciones, clientes y usuarios. Cada
    consulta resuelve todo el lote con una sola lectura; los ids sin dato se omiten.
    """

    async def client_names(self, client_ids: Collection[UUID]) -> Mapping[UUID, str]:
        """Nombre completo de cada cliente registrado."""

    async def user_names(self, user_ids: Collection[UUID]) -> Mapping[UUID, str]:
        """Nombre completo de cada usuario del panel."""

    async def quote_statuses(self, quote_ids: Collection[UUID]) -> Mapping[UUID, QuoteStatus]:
        """Estado de cada cotización."""
