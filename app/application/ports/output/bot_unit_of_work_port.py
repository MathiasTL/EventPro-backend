"""Unidad de trabajo del bot de WhatsApp: una transacción que comparten sus casos de uso.

Fuera de HTTP no hay una sesión por petición que confirme sola (spec 08, sección 2.4). El bot
abre una unidad de trabajo por turno de conversación: ``CreateQuote``, ``PayAdvance`` y
``EnqueueMessage`` leen y escriben con la misma sesión, de modo que la cotización y su
resumen de WhatsApp se confirman juntos o ninguno queda.
"""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass

from app.application.ports.input.quote_create_port import ICreateQuotePort
from app.application.ports.input.quote_lifecycle_port import IPayAdvancePort
from app.application.ports.output.catalog_read_port import ICatalogReadPort
from app.application.use_cases.messaging.enqueue_message import EnqueueMessage


@dataclass(frozen=True)
class BotTransaction:
    """Casos de uso y lecturas que el bot ejecuta dentro de una misma transacción."""

    create_quote: ICreateQuotePort
    pay_advance: IPayAdvancePort
    enqueue_message: EnqueueMessage
    catalog: ICatalogReadPort


# Abre la unidad de trabajo: confirma al salir sin error y revierte si el bloque falla.
BotUnitOfWork = Callable[[], AbstractAsyncContextManager[BotTransaction]]
