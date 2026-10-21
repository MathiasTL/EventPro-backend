"""Tomar, devolver y reasignar con compensación (spec 09, 6.3, 6.5, 6.6; D8, D9, D11, D18, D23)."""

from collections.abc import Awaitable, Callable

import pytest

from app.application.dtos.messaging_dto import ConversationLifecycle, ConversationStatus
from app.domain.entities.conversation_link import HandoffReason
from app.domain.exceptions.messaging_exceptions import (
    ConversationNotTakenError,
    ConversationTakenByOtherError,
    MessagingUnavailableError,
)
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.secondary.external_services.fake_messaging_adapter import (
    FakeMessagingAdapter,
)
from tests.application.assignment_support import NOW, PHONE, AssignmentWorld, new_user

ENCARGADO = Role.ENCARGADO
SUPERADMIN = Role.SUPERADMIN


async def _lifecycle(world: AssignmentWorld) -> ConversationLifecycle:
    return (await world.messaging.get_conversation(world.conversation_id)).lifecycle


# --- takeover -----------------------------------------------------------------------------


async def test_takeover_of_a_pending_conversation_opens_assigns_and_records_the_handoff() -> None:
    world, user = AssignmentWorld(), new_user()

    view = await world.takeover.execute(1, user_id=user, role=ENCARGADO)

    assert (view.lifecycle, view.mode, view.assigned_user_id) == (
        ConversationLifecycle.OPEN,
        ConversationStatus.HUMAN,
        user,
    )
    link = world.stored()
    assert link.assigned_user_id == user
    assert (link.handoff_reason, link.handed_off_at) == (HandoffReason.MANUAL_TAKEOVER, NOW)
    assert await _lifecycle(world) is ConversationLifecycle.OPEN
    assert [e.data["assigned_user_id"] for e in world.publisher.events] == [str(user)]
    assert world.audit_port.entries == []


async def test_takeover_from_pending_clears_the_bot_session() -> None:
    world = AssignmentWorld()
    await world.sessions.save(1, {"step": "quote"})

    await world.takeover.execute(1, user_id=new_user(), role=ENCARGADO)

    assert await world.sessions.get(1) is None


async def test_takeover_from_resolved_reopens_with_manual_takeover() -> None:
    world, user = AssignmentWorld(), new_user()
    world.messaging.resolve_conversation(1)
    await world.sessions.save(1, {"step": "quote"})

    view = await world.takeover.execute(1, user_id=user, role=ENCARGADO)

    assert view.lifecycle is ConversationLifecycle.OPEN
    assert await _lifecycle(world) is ConversationLifecycle.OPEN
    assert world.stored().handoff_reason is HandoffReason.MANUAL_TAKEOVER
    assert await world.sessions.get(1) is None


async def test_takeover_of_an_open_unassigned_handoff_keeps_the_original_reason() -> None:
    world, user = AssignmentWorld(), new_user()
    await world.open_unassigned(HandoffReason.CLIENT_REQUEST)
    await world.sessions.save(1, {"step": "kept"})

    await world.takeover.execute(1, user_id=user, role=ENCARGADO)

    link = world.stored()
    assert link.assigned_user_id == user
    assert (link.handoff_reason, link.handed_off_at) == (HandoffReason.CLIENT_REQUEST, NOW)
    assert await world.sessions.get(1) == {"step": "kept"}


async def test_takeover_by_the_same_user_is_idempotent() -> None:
    world, user = AssignmentWorld(), new_user()
    await world.takeover.execute(1, user_id=user, role=ENCARGADO)
    published = len(world.publisher.events)

    view = await world.takeover.execute(1, user_id=user, role=ENCARGADO)

    assert view.assigned_user_id == user
    assert len(world.publisher.events) == published
    assert world.audit_port.entries == []


async def test_encargado_cannot_take_a_conversation_assigned_to_another() -> None:
    world, owner = AssignmentWorld(), new_user()
    await world.assign(owner)

    with pytest.raises(ConversationTakenByOtherError) as raised:
        await world.takeover.execute(1, user_id=new_user(), role=ENCARGADO)

    assert raised.value.assigned_user_id == owner
    assert world.stored().assigned_user_id == owner
    assert world.audit_port.entries == []


async def test_a_leftover_assignment_on_a_pending_conversation_blocks_another_encargado() -> None:
    # Con Chatwoot aún en ``pending`` la toma de otro puede estar en curso: no se pisa.
    world, owner = AssignmentWorld(), new_user()
    await world.assign(owner)
    await world.messaging.set_conversation_status(1, ConversationStatus.BOT)

    with pytest.raises(ConversationTakenByOtherError) as raised:
        await world.takeover.execute(1, user_id=new_user(), role=ENCARGADO)

    assert raised.value.assigned_user_id == owner
    assert world.stored().assigned_user_id == owner


async def test_the_owner_of_a_leftover_assignment_retakes_and_reopens() -> None:
    world, owner = AssignmentWorld(), new_user()
    await world.assign(owner)
    await world.messaging.set_conversation_status(1, ConversationStatus.BOT)

    view = await world.takeover.execute(1, user_id=owner, role=ENCARGADO)

    assert (view.lifecycle, view.assigned_user_id) == (ConversationLifecycle.OPEN, owner)
    assert world.audit_port.entries == []


async def test_superadmin_reassigns_and_audits_the_override_with_old_and_new_assignee() -> None:
    world, owner, admin = AssignmentWorld(), new_user(), new_user()
    await world.assign(owner)

    view = await world.takeover.execute(1, user_id=admin, role=SUPERADMIN)

    assert view.assigned_user_id == admin
    assert world.stored().assigned_user_id == admin
    (entry,) = world.audit_port.entries
    assert entry.action == "OVERRIDE_CONVERSATION_ASSIGNMENT"
    assert (entry.entity_name, entry.entity_id, entry.user_id) == (
        "conversation_link",
        world.stored().id,
        admin,
    )
    assert entry.old_values == {"assigned_user_id": str(owner)}
    assert entry.new_values == {"assigned_user_id": str(admin)}
    assert len(world.publisher.events) == 1


async def test_superadmin_taking_an_unassigned_conversation_is_not_audited() -> None:
    world = AssignmentWorld()

    await world.takeover.execute(1, user_id=new_user(), role=SUPERADMIN)

    assert world.audit_port.entries == []


async def test_a_lost_claim_is_a_conflict_with_the_winner_and_changes_nothing_else() -> None:
    world, winner = AssignmentWorld(), new_user()
    await world.open_unassigned()
    real_claim = world.links.claim

    async def lose_race(conversation_id, user_id, expected):  # type: ignore[no-untyped-def]
        await real_claim(conversation_id, winner, None)  # el otro encargado gana antes
        return await real_claim(conversation_id, user_id, expected)

    world.links.claim = lose_race  # type: ignore[method-assign]

    with pytest.raises(ConversationTakenByOtherError) as raised:
        await world.takeover.execute(1, user_id=new_user(), role=ENCARGADO)

    assert raised.value.assigned_user_id == winner
    assert world.stored().assigned_user_id == winner
    assert world.publisher.events == []


async def test_a_chatwoot_failure_on_reopen_compensates_the_assignment() -> None:
    world = AssignmentWorld()
    world.messaging.status_update_fails = True

    with pytest.raises(MessagingUnavailableError):
        await world.takeover.execute(1, user_id=new_user(), role=ENCARGADO)

    assert world.stored().assigned_user_id is None
    assert world.stored().handoff_reason is None
    assert world.publisher.events == []


async def test_a_chatwoot_failure_on_a_superadmin_reassignment_restores_the_previous_holder() -> (
    None
):
    world, owner, admin = AssignmentWorld(), new_user(), new_user()
    await world.assign(owner)
    world.messaging.status_update_fails = True

    with pytest.raises(MessagingUnavailableError):
        await world.takeover.execute(1, user_id=admin, role=SUPERADMIN)

    assert world.stored().assigned_user_id == owner
    assert world.audit_port.entries == []
    assert world.publisher.events == []


async def test_a_failed_compensation_does_not_mask_the_original_chatwoot_error() -> None:
    world, owner, admin = AssignmentWorld(), new_user(), new_user()
    await world.assign(owner)
    world.messaging.status_update_fails = True
    real_claim = world.links.claim
    calls = 0

    async def fail_on_compensation(conversation_id, user_id, expected):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        if calls > 1:
            raise RuntimeError("la base de datos no responde")
        return await real_claim(conversation_id, user_id, expected)

    world.links.claim = fail_on_compensation  # type: ignore[method-assign]

    with pytest.raises(MessagingUnavailableError):
        await world.takeover.execute(1, user_id=admin, role=SUPERADMIN)

    assert calls == 2


async def test_takeover_of_a_missing_conversation_is_not_found_and_creates_no_link() -> None:
    world = AssignmentWorld()

    with pytest.raises(ResourceNotFoundError):
        await world.takeover.execute(99, user_id=new_user(), role=ENCARGADO)

    assert world.links.links == {}


async def test_a_session_or_publish_failure_does_not_revert_the_takeover() -> None:
    world, user = AssignmentWorld(), new_user()

    class _Broken:
        async def clear(self, conversation_id: int) -> None:
            raise RuntimeError("redis caído")

        async def publish(self, event: object) -> None:
            raise RuntimeError("redis caído")

    world.takeover._sessions = _Broken()  # type: ignore[attr-defined]
    world.takeover._publisher = _Broken()  # type: ignore[attr-defined]

    view = await world.takeover.execute(1, user_id=user, role=ENCARGADO)

    assert view.assigned_user_id == user
    assert world.stored().assigned_user_id == user


# --- release ------------------------------------------------------------------------------


async def test_release_by_the_assignee_returns_the_conversation_to_the_bot() -> None:
    world, user = AssignmentWorld(), new_user()
    await world.takeover.execute(1, user_id=user, role=ENCARGADO)
    world.publisher.events.clear()

    view = await world.release.execute(1, user_id=user, role=ENCARGADO)

    assert (view.lifecycle, view.mode, view.assigned_user_id) == (
        ConversationLifecycle.PENDING,
        ConversationStatus.BOT,
        None,
    )
    link = world.stored()
    assert link.assigned_user_id is None
    assert link.handoff_reason is HandoffReason.MANUAL_TAKEOVER  # historial conservado
    assert await _lifecycle(world) is ConversationLifecycle.PENDING
    assert [e.data["mode"] for e in world.publisher.events] == ["BOT"]
    assert world.audit_port.entries == []


async def test_release_of_a_pending_conversation_is_idempotent() -> None:
    world = AssignmentWorld()

    view = await world.release.execute(1, user_id=new_user(), role=ENCARGADO)

    assert view.lifecycle is ConversationLifecycle.PENDING
    assert world.publisher.events == []
    assert world.uow.opened == 0


async def test_release_of_a_resolved_conversation_without_assignee_is_a_no_op() -> None:
    world = AssignmentWorld()
    world.messaging.resolve_conversation(1)

    view = await world.release.execute(1, user_id=new_user(), role=ENCARGADO)

    assert view.lifecycle is ConversationLifecycle.RESOLVED
    assert world.publisher.events == []


async def test_another_encargado_cannot_release() -> None:
    world, owner = AssignmentWorld(), new_user()
    await world.assign(owner)

    with pytest.raises(ConversationTakenByOtherError) as raised:
        await world.release.execute(1, user_id=new_user(), role=ENCARGADO)

    assert raised.value.assigned_user_id == owner
    assert world.stored().assigned_user_id == owner
    assert await _lifecycle(world) is ConversationLifecycle.OPEN


async def test_encargado_releasing_an_open_unassigned_conversation_is_not_taken() -> None:
    world = AssignmentWorld()
    await world.open_unassigned()

    with pytest.raises(ConversationNotTakenError):
        await world.release.execute(1, user_id=new_user(), role=ENCARGADO)

    assert await _lifecycle(world) is ConversationLifecycle.OPEN


async def test_superadmin_releasing_anothers_conversation_audits_the_override() -> None:
    world, owner, admin = AssignmentWorld(), new_user(), new_user()
    await world.assign(owner)

    view = await world.release.execute(1, user_id=admin, role=SUPERADMIN)

    assert view.lifecycle is ConversationLifecycle.PENDING
    assert world.stored().assigned_user_id is None
    (entry,) = world.audit_port.entries
    assert entry.action == "OVERRIDE_CONVERSATION_ASSIGNMENT"
    assert (entry.entity_name, entry.entity_id, entry.user_id) == (
        "conversation_link",
        world.stored().id,
        admin,
    )
    assert entry.old_values == {"assigned_user_id": str(owner)}
    assert entry.new_values == {"assigned_user_id": None}


async def test_superadmin_releasing_an_unassigned_open_conversation_returns_it_to_the_bot() -> None:
    world = AssignmentWorld()
    await world.open_unassigned()

    view = await world.release.execute(1, user_id=new_user(), role=SUPERADMIN)

    assert view.lifecycle is ConversationLifecycle.PENDING
    assert world.audit_port.entries == []


async def test_a_chatwoot_failure_on_release_restores_the_assignment() -> None:
    world, user = AssignmentWorld(), new_user()
    await world.takeover.execute(1, user_id=user, role=ENCARGADO)
    world.publisher.events.clear()
    world.messaging.status_update_fails = True

    with pytest.raises(MessagingUnavailableError):
        await world.release.execute(1, user_id=user, role=ENCARGADO)

    assert world.stored().assigned_user_id == user
    assert await _lifecycle(world) is ConversationLifecycle.OPEN
    assert world.publisher.events == []
    assert world.audit_port.entries == []


async def test_a_lost_release_cas_returns_the_current_view_without_flipping_back() -> None:
    world, user, admin = AssignmentWorld(), new_user(), new_user()
    await world.assign(user)
    real_release = world.links.release

    async def reassigned_meanwhile(conversation_id, expected):  # type: ignore[no-untyped-def]
        await world.links.claim(conversation_id, admin, expected)  # un SUPERADMIN reasigna
        return await real_release(conversation_id, expected)

    world.links.release = reassigned_meanwhile  # type: ignore[method-assign]

    view = await world.release.execute(1, user_id=user, role=ENCARGADO)

    assert world.stored().assigned_user_id == admin
    assert view.lifecycle is ConversationLifecycle.PENDING
    assert await _lifecycle(world) is ConversationLifecycle.PENDING  # no se revierte Chatwoot


class _InterleavingMessaging(FakeMessagingAdapter):
    """Corre ``during`` justo antes de aplicar un cambio de estado de Chatwoot."""

    def __init__(self) -> None:
        super().__init__()
        self.before_status: list[Callable[[ConversationStatus], Awaitable[None]]] = []

    async def set_conversation_status(
        self, conversation_id: int, status: ConversationStatus
    ) -> None:
        while self.before_status:
            await self.before_status.pop()(status)
        await super().set_conversation_status(conversation_id, status)


async def test_a_takeover_during_the_release_call_is_rejected_until_the_release_completes() -> None:
    world, releaser, other = AssignmentWorld(), new_user(), new_user()
    world.messaging = _InterleavingMessaging()
    world.messaging.receive_text(PHONE, "Hola", name="Carlos")
    world.release._messaging = world.messaging  # type: ignore[attr-defined]
    world.takeover._messaging = world.messaging  # type: ignore[attr-defined]
    await world.takeover.execute(1, user_id=releaser, role=ENCARGADO)
    attempts: list[object] = []

    async def other_takes_over(status: ConversationStatus) -> None:
        try:
            attempts.append(await world.takeover.execute(1, user_id=other, role=ENCARGADO))
        except ConversationTakenByOtherError as exc:
            attempts.append(exc)

    world.messaging.before_status.append(other_takes_over)  # type: ignore[attr-defined]

    await world.release.execute(1, user_id=releaser, role=ENCARGADO)

    (attempt,) = attempts
    assert isinstance(attempt, ConversationTakenByOtherError)
    assert attempt.assigned_user_id == releaser
    assert world.stored().assigned_user_id is None
    assert await _lifecycle(world) is ConversationLifecycle.PENDING


async def test_a_takeover_with_a_stale_open_read_still_reopens_in_chatwoot() -> None:
    world, user = AssignmentWorld(), new_user()
    world.messaging = _InterleavingMessaging()
    world.messaging.receive_text(PHONE, "Hola", name="Carlos")
    world.takeover._messaging = world.messaging  # type: ignore[attr-defined]
    await world.open_unassigned()
    await world.messaging.set_conversation_status(1, ConversationStatus.HUMAN)
    real_get = world.messaging.get_conversation

    async def stale_open(conversation_id: int):  # type: ignore[no-untyped-def]
        summary = await real_get(conversation_id)  # lo lee ``open``...
        await world.messaging.set_conversation_status(1, ConversationStatus.BOT)  # ...y se devuelve
        return summary

    world.messaging.get_conversation = stale_open  # type: ignore[method-assign]

    view = await world.takeover.execute(1, user_id=user, role=ENCARGADO)

    assert view.assigned_user_id == user
    assert world.stored().assigned_user_id == user
    assert await _lifecycle(world) is ConversationLifecycle.OPEN
