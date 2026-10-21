"""Autoría de un mensaje de la bandeja (spec 09, sección 4.3, D3). Función pura."""

from app.application.dtos.messaging_dto import AuthorType, MessageDirection, MessageSender
from app.domain.entities.outbox_message import OutboxMessage


def resolve_author_type(
    *,
    direction: MessageDirection,
    outbox: OutboxMessage | None,
    sender: MessageSender | None,
) -> AuthorType | None:
    """Autor del mensaje, o ``None`` para un aviso de actividad (nunca es del bot).

    Un entrante es del cliente. Un saliente se resuelve primero por el outbox (con
    ``author_user_id`` es un encargado; sin él, el bot) y después por el remitente de
    Chatwoot (``user`` es un encargado, ``agent_bot`` el bot). Sin fila ni remitente
    conocido gana ``BOT``: un humano solo escribe por EventPro y eso siempre deja fila.
    """

    if direction is MessageDirection.ACTIVITY:
        return None
    if direction is MessageDirection.INCOMING:
        return AuthorType.CLIENT
    if outbox is not None:
        return AuthorType.AGENT if outbox.author_user_id is not None else AuthorType.BOT
    if sender is MessageSender.USER:
        return AuthorType.AGENT
    return AuthorType.BOT
