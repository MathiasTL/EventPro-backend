"""Unidad de trabajo corta de ``conversation_links`` (spec 09, D11).

Cada bloque abre su propia transacción y confirma al salir sin error. Tomar y devolver las
usan en tramos separados para no mantener una transacción abierta durante la llamada HTTP a
Chatwoot.
"""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from app.application.ports.output.conversation_link_repository_port import (
    IConversationLinkRepositoryPort,
)

ConversationLinkUnitOfWork = Callable[
    [], AbstractAsyncContextManager[IConversationLinkRepositoryPort]
]
