from collections.abc import Callable, Collection, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from app.domain.entities.outbox_message import OutboxMessage
from app.domain.value_objects.phone_number import PhoneNumber


class IOutboxRepositoryPort(Protocol):
    """Persistencia de OutboxMessage. Nunca confirma: la transacción es del llamador."""

    async def add(self, message: OutboxMessage) -> OutboxMessage:
        """Inserta un mensaje nuevo en la sesión del llamador; falla si el id ya existe."""

    async def save(self, message: OutboxMessage) -> OutboxMessage:
        """Actualiza un mensaje existente; lanza ResourceNotFoundError si no existe."""

    async def get_by_id(
        self, message_id: UUID, *, for_update: bool = False
    ) -> OutboxMessage | None:
        """Devuelve el mensaje o None; ``for_update`` bloquea la fila hasta el cierre."""

    async def get_by_external_id(
        self, external_message_id: str, *, for_update: bool = False
    ) -> OutboxMessage | None:
        """Busca por el identificador que asignó Chatwoot; ``for_update`` bloquea la fila."""

    async def find_by_message_reference(self, external_message_id: str) -> OutboxMessage | None:
        """Busca por el id externo actual o por el que conservó un reintento (D24)."""

    async def get_many_by_external_ids(
        self, external_message_ids: Collection[str]
    ) -> Mapping[str, OutboxMessage]:
        """Filas del lote por id externo, actual o conservado por un reintento (D24).

        La clave es cada id pedido que coincidió; los ids sin fila se omiten.
        """

    async def list_unsent_for_recipient(
        self, phone: PhoneNumber, *, limit: int = 50
    ) -> Sequence[OutboxMessage]:
        """Filas del destinatario que no llegaron a Chatwoot (``PENDING`` o ``FAILED``).

        Las más antiguas primero; sirve a ``unsent`` de la primera página del hilo (6.7).
        """

    async def claim_due(
        self, *, now: datetime, limit: int, lease: timedelta
    ) -> Sequence[OutboxMessage]:
        """Reserva hasta ``limit`` mensajes ``PENDING`` con ``next_attempt_at <= now``.

        Las filas ya reservadas por otra transacción se omiten, y cada mensaje devuelto
        adelanta su ``next_attempt_at`` a ``now + lease`` (reserva con vencimiento): si el
        worker muere antes de guardar el resultado, el mensaje vuelve a estar disponible
        cuando vence la reserva. Los más antiguos van primero.
        """


# Abre una transacción corta: confirma al salir sin error y revierte si el bloque falla.
OutboxTransactionFactory = Callable[[], AbstractAsyncContextManager[IOutboxRepositoryPort]]
