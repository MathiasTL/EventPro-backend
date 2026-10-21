from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.domain.entities.conversation_link import ConversationLink, HandoffReason
from app.domain.exceptions.resource_exceptions import ValidationError

NOW = datetime(2026, 10, 20, 15, 0, tzinfo=UTC)
LATER = NOW + timedelta(hours=2)
NAIVE = datetime(2026, 10, 20, 15, 0)


def _link(**overrides: object) -> ConversationLink:
    return ConversationLink.create(chatwoot_conversation_id=10, now=NOW, **overrides)  # type: ignore[arg-type]


def test_create_starts_unassigned_without_client_or_handoff() -> None:
    link = _link()

    assert link.chatwoot_conversation_id == 10
    assert link.client_id is None
    assert link.assigned_user_id is None
    assert link.handoff_reason is None
    assert link.last_client_message_at is None
    assert link.created_at == link.updated_at == NOW


def test_create_keeps_the_client_when_known() -> None:
    client = uuid4()
    assert _link(client_id=client).client_id == client


@pytest.mark.parametrize("bad", [0, -1, True, "7"])
def test_create_rejects_an_invalid_conversation_id(bad: object) -> None:
    with pytest.raises(ValidationError):
        ConversationLink.create(chatwoot_conversation_id=bad, now=NOW)  # type: ignore[arg-type]


def test_timestamps_must_carry_a_timezone_and_are_normalized_to_utc() -> None:
    with pytest.raises(ValidationError):
        ConversationLink.create(chatwoot_conversation_id=1, now=NAIVE)
    link = _link()
    link.record_client_message(datetime(2026, 10, 20, 10, 0, tzinfo=timezone(timedelta(hours=-5))))
    assert link.last_client_message_at == NOW


def test_register_handoff_replaces_the_previous_one() -> None:
    link = _link()
    link.register_handoff(reason=HandoffReason.BOT_ERROR, summary="  Error  ", at=NOW)
    link.register_handoff(reason=HandoffReason.CLIENT_REQUEST, summary=None, at=LATER)

    assert link.handoff_reason is HandoffReason.CLIENT_REQUEST
    assert link.handoff_summary is None
    assert link.handed_off_at == LATER
    assert link.updated_at == LATER


def test_register_handoff_clips_and_blanks_the_summary() -> None:
    link = _link()
    link.register_handoff(reason=HandoffReason.BOT_ERROR, summary="x" * 5000, at=NOW)
    assert link.handoff_summary is not None
    assert len(link.handoff_summary) == 4000
    link.register_handoff(reason=HandoffReason.BOT_ERROR, summary="   ", at=NOW)
    assert link.handoff_summary is None


def test_register_handoff_rejects_a_non_enum_reason() -> None:
    with pytest.raises(ValidationError):
        _link().register_handoff(reason="OTHER", summary=None, at=NOW)  # type: ignore[arg-type]


def test_assign_unassign_and_link_quote_touch_updated_at() -> None:
    link = _link()
    user, quote = uuid4(), uuid4()

    link.assign(user, at=LATER)
    assert (link.assigned_user_id, link.updated_at) == (user, LATER)
    link.unassign(at=LATER + timedelta(minutes=1))
    assert link.assigned_user_id is None
    link.link_quote(quote, at=LATER)
    assert link.quote_id == quote
    link.link_quote(None, at=LATER)
    assert link.quote_id is None


def test_record_client_message_never_moves_backwards() -> None:
    link = _link()
    link.record_client_message(LATER)
    link.record_client_message(NOW)

    assert link.last_client_message_at == LATER


def test_mark_event_done_is_idempotent_and_keeps_the_first_author() -> None:
    link = _link()
    first, second = uuid4(), uuid4()

    link.mark_event_done(user_id=first, at=NOW)
    link.mark_event_done(user_id=second, at=LATER)

    assert (link.event_done_at, link.event_done_by_user_id) == (NOW, first)


def test_restart_lead_cycle_clears_the_mark_and_unlinks_the_quote() -> None:
    link = _link()
    link.link_quote(uuid4(), at=NOW)
    link.mark_event_done(user_id=uuid4(), at=NOW)

    link.restart_lead_cycle(at=LATER)

    assert link.lead_cycle_started_at == LATER
    assert link.event_done_at is None
    assert link.event_done_by_user_id is None
    assert link.quote_id is None
