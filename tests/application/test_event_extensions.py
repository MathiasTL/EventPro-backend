from copy import deepcopy
from decimal import Decimal
from uuid import uuid4

import pytest

from app.application.dtos.event_schedule_dto import ScheduleActor
from app.application.use_cases.event.register_event_extension import RegisterEventExtensionUseCase
from app.application.use_cases.event.settle_event import SettleEventUseCase
from app.domain.entities.payment import PaymentAuditStatus, PaymentConcept, PaymentValidationStatus
from app.domain.exceptions.event_exceptions import BalancePendingError, InvalidEventStateError
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError, ValidationError
from app.domain.value_objects.event_status import EventStatus
from app.domain.value_objects.money import Money
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.secondary.external_services.fake_schedule_adapters import (
    FakeCrewScheduleReadAdapter,
)
from tests.event_support import make_event
from tests.extension_support import (
    FakeExtensionRepository,
    RecordingEvidenceStorage,
    extension_input,
)
from tests.start_event_support import STARTED_AT, FixedClock


def setup(status=EventStatus.IN_PROGRESS, role=Role.ENCARGADO):
    event = make_event(status=status, pre_show_balance_paid=Money(Decimal("980.50")))
    actor = ScheduleActor(uuid4(), role)
    repo, storage = FakeExtensionRepository((event,)), RecordingEvidenceStorage()
    crews = FakeCrewScheduleReadAdapter(
        assigned_events_by_user={actor.user_id: frozenset({event.id})}
    )
    return event, actor, repo, storage, crews


@pytest.mark.parametrize("role", list(Role))
async def test_extension_creates_real_verified_payment_and_settles(role):
    event, actor, repo, storage, crews = setup(role=role)
    result = await RegisterEventExtensionUseCase(repo, storage, crews, FixedClock()).execute(
        extension_input(event.id), actor
    )
    payment, extension = repo.payments[0], repo.extensions[0]
    assert result.status is EventStatus.EXTENDED
    assert result.extension_id == extension.id
    assert result.payment.payment_id == payment.id == extension.payment_id
    assert payment.concept is PaymentConcept.EXTENSION
    assert payment.validation_status is PaymentValidationStatus.VERIFIED
    assert payment.audit_status is PaymentAuditStatus.UNREVIEWED
    assert payment.registered_by_user_id == actor.user_id
    assert payment.verified_at is payment.verified_by_user_id is None
    assert payment.quote_id == event.quote_id
    assert payment.created_at == extension.requested_at == STARTED_AT
    closed = await SettleEventUseCase(repo, crews).execute(event.id, actor)
    assert closed.status is EventStatus.SETTLED
    assert repo.events[event.id].final_total_amount == Money(Decimal("1180.50"))


async def test_operator_outside_scope_is_not_found_before_load_or_storage():
    event, _, repo, storage, _ = setup()
    actor = ScheduleActor(uuid4(), Role.OPERADOR)
    crews = FakeCrewScheduleReadAdapter()
    with pytest.raises(ResourceNotFoundError):
        await RegisterEventExtensionUseCase(repo, storage, crews, FixedClock()).execute(
            extension_input(event.id), actor
        )
    with pytest.raises(ResourceNotFoundError):
        await SettleEventUseCase(repo, crews).execute(event.id, actor)
    assert repo.loads == storage.paths == repo.saves == []


async def test_missing_event_compensates_evidence():
    _, actor, repo, storage, crews = setup()
    with pytest.raises(ResourceNotFoundError):
        await RegisterEventExtensionUseCase(repo, storage, crews, FixedClock()).execute(
            extension_input(uuid4()), actor
        )
    assert storage.deleted == storage.paths
    assert repo.saves == []


@pytest.mark.parametrize("status", [EventStatus.SCHEDULED, EventStatus.SETTLED])
async def test_invalid_state_compensates_storage_without_payment_reads(status):
    event, actor, repo, storage, crews = setup(status)
    with pytest.raises(InvalidEventStateError):
        await RegisterEventExtensionUseCase(repo, storage, crews, FixedClock()).execute(
            extension_input(event.id), actor
        )
    with pytest.raises(InvalidEventStateError):
        await SettleEventUseCase(repo, crews).execute(event.id, actor)
    assert storage.deleted == storage.paths
    assert repo.saves == repo.total_reads == []


@pytest.mark.parametrize(
    "changes",
    [
        dict(extra_minutes=0),
        dict(agreed_rate=Decimal("0")),
        dict(transaction_reference=" "),
        dict(transaction_reference="x" * 61),
    ],
)
async def test_invalid_input_is_rejected_before_storing(changes):
    event, actor, repo, storage, crews = setup()
    with pytest.raises(ValidationError):
        await RegisterEventExtensionUseCase(repo, storage, crews, FixedClock()).execute(
            extension_input(event.id, **changes), actor
        )
    assert storage.paths == repo.saves == []


@pytest.mark.parametrize("cleanup_fails", [False, True])
async def test_save_failure_compensates_evidence_and_preserves_original_error(cleanup_fails):
    event, actor, repo, storage, crews = setup()
    original = deepcopy(event)
    repo.fail_save = True
    storage.fail_delete = cleanup_fails
    with pytest.raises(RuntimeError, match="persistir"):
        await RegisterEventExtensionUseCase(repo, storage, crews, FixedClock()).execute(
            extension_input(event.id), actor
        )
    assert storage.deleted == storage.paths
    assert repo.events[event.id] == original
    assert repo.payments == repo.extensions == []


async def test_settle_uses_saved_base_amounts_but_requires_complete_coverage():
    event, actor, repo, _, crews = setup()
    repo.events[event.id].pre_show_balance_paid = Money.zero()
    with pytest.raises(BalancePendingError):
        await SettleEventUseCase(repo, crews).execute(event.id, actor)
    assert repo.saves == []
    repo.events[event.id].pre_show_balance_paid = Money(Decimal("980.50"))
    assert (
        await SettleEventUseCase(repo, crews).execute(event.id, actor)
    ).status is EventStatus.SETTLED


async def test_store_failure_never_saves_event_or_payment():
    event, actor, repo, storage, crews = setup()
    storage.fail_store = True
    with pytest.raises(ValueError, match="storage failed"):
        await RegisterEventExtensionUseCase(repo, storage, crews, FixedClock()).execute(
            extension_input(event.id), actor
        )
    assert repo.events[event.id] == event
    assert repo.saves == storage.deleted == []


async def test_evidence_is_preserved_when_commit_succeeded_but_acknowledgement_failed():
    event, actor, _, storage, crews = setup()

    class LostAcknowledgementRepository(FakeExtensionRepository):
        async def save_extension(self, event, extension, payment):
            await super().save_extension(event, extension, payment)
            raise RuntimeError("commit acknowledgement lost")

    repo = LostAcknowledgementRepository((event,))
    with pytest.raises(RuntimeError, match="acknowledgement"):
        await RegisterEventExtensionUseCase(repo, storage, crews, FixedClock()).execute(
            extension_input(event.id), actor
        )
    assert repo.payments[0].evidence_path == storage.paths[0]
    assert storage.deleted == []


@pytest.mark.parametrize("rate", [Decimal("1.001"), Decimal("Infinity"), Decimal("1E+100")])
async def test_nonrepresentable_rate_is_rejected_before_storage(rate):
    event, actor, repo, storage, crews = setup()
    with pytest.raises(ValidationError):
        await RegisterEventExtensionUseCase(repo, storage, crews, FixedClock()).execute(
            extension_input(event.id, agreed_rate=rate), actor
        )
    assert storage.paths == repo.saves == []
