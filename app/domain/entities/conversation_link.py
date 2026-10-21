"""Agregado ConversationLink: vínculo entre una conversación de Chatwoot y datos de EventPro.

Es lo único que EventPro persiste de una conversación (ADR-10): cliente, cotización vigente,
encargado asignado, última derivación, última marca del cliente y etapa «Evento realizado».
Los mensajes viven solo en Chatwoot.

La asignación (``assigned_user_id``) la decide el repositorio con *compare-and-set*
(``claim``/``release``); ``assign`` y ``unassign`` solo reflejan ese resultado en la
instancia ya cargada.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Self
from uuid import UUID, uuid4

from app.domain.exceptions.resource_exceptions import ValidationError

_SUMMARY_MAX_LENGTH = 4000


class HandoffReason(StrEnum):
    """Motivo de la última derivación a un humano."""

    CLIENT_REQUEST = "CLIENT_REQUEST"
    BOT_NOT_UNDERSTOOD = "BOT_NOT_UNDERSTOOD"
    MANUAL_TAKEOVER = "MANUAL_TAKEOVER"
    BOT_ERROR = "BOT_ERROR"


def _require_aware(value: datetime, name: str) -> datetime:
    """Exige un instante con zona horaria y lo normaliza a UTC."""

    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError(f"{name} debe incluir zona horaria")
    return value.astimezone(UTC)


@dataclass(kw_only=True)
class ConversationLink:
    chatwoot_conversation_id: int
    created_at: datetime
    updated_at: datetime
    client_id: UUID | None = None
    quote_id: UUID | None = None
    assigned_user_id: UUID | None = None
    handoff_reason: HandoffReason | None = None
    handoff_summary: str | None = None
    handed_off_at: datetime | None = None
    last_client_message_at: datetime | None = None
    event_done_at: datetime | None = None
    event_done_by_user_id: UUID | None = None
    lead_cycle_started_at: datetime | None = None
    id: UUID = field(default_factory=uuid4)

    @classmethod
    def create(
        cls,
        *,
        chatwoot_conversation_id: int,
        now: datetime,
        client_id: UUID | None = None,
    ) -> Self:
        """Vínculo nuevo: sin asignado, sin derivación y, si no hay cliente, ``client_id`` nulo."""

        if (
            isinstance(chatwoot_conversation_id, bool)
            or not isinstance(chatwoot_conversation_id, int)
            or chatwoot_conversation_id < 1
        ):
            raise ValidationError("chatwoot_conversation_id debe ser un entero positivo")
        moment = _require_aware(now, "now")
        return cls(
            chatwoot_conversation_id=chatwoot_conversation_id,
            client_id=client_id,
            created_at=moment,
            updated_at=moment,
        )

    def register_handoff(self, *, reason: HandoffReason, summary: str | None, at: datetime) -> None:
        """Registra la última derivación a un humano; reemplaza el motivo y el resumen previos."""

        if not isinstance(reason, HandoffReason):
            raise ValidationError("reason debe ser un HandoffReason")
        moment = _require_aware(at, "at")
        self.handoff_reason = reason
        self.handoff_summary = _clip_summary(summary)
        self.handed_off_at = moment
        self.updated_at = moment

    def assign(self, user_id: UUID, *, at: datetime) -> None:
        self.assigned_user_id = user_id
        self.updated_at = _require_aware(at, "at")

    def unassign(self, *, at: datetime) -> None:
        self.assigned_user_id = None
        self.updated_at = _require_aware(at, "at")

    def link_quote(self, quote_id: UUID | None, *, at: datetime) -> None:
        """Fija la cotización vigente; ``None`` la desvincula sin borrarla."""

        self.quote_id = quote_id
        self.updated_at = _require_aware(at, "at")

    def record_client_message(self, at: datetime) -> None:
        """Anota el último mensaje entrante; nunca retrocede ante un evento fuera de orden."""

        moment = _require_aware(at, "at")
        if self.last_client_message_at is None or moment > self.last_client_message_at:
            self.last_client_message_at = moment
        self.updated_at = max(self.updated_at, moment)

    def mark_event_done(self, *, user_id: UUID, at: datetime) -> None:
        """Marca manual de «Evento realizado» (D25); idempotente si ya estaba marcado."""

        if self.event_done_at is not None:
            return
        moment = _require_aware(at, "at")
        self.event_done_at = moment
        self.event_done_by_user_id = user_id
        self.updated_at = moment

    def restart_lead_cycle(self, *, at: datetime) -> None:
        """El cliente volvió tras «Evento realizado»: nuevo ciclo comercial (D25).

        Limpia la marca manual y desvincula la cotización anterior sin borrarla.
        """

        moment = _require_aware(at, "at")
        self.lead_cycle_started_at = moment
        self.event_done_at = None
        self.event_done_by_user_id = None
        self.quote_id = None
        self.updated_at = moment


def _clip_summary(summary: str | None) -> str | None:
    if summary is None:
        return None
    return summary.strip()[:_SUMMARY_MAX_LENGTH] or None
