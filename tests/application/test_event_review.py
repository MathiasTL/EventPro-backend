from decimal import Decimal

import pytest

from app.application.use_cases.event.register_event_extension import RegisterEventExtensionUseCase
from app.domain.exceptions.event_exceptions import EventResourceConflictError
from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.event_status import EventStatus
from tests.application.test_event_extensions import setup
from tests.extension_support import extension_input
from tests.start_event_support import FixedClock


async def test_invalid_terms_on_settled_event_never_load_or_lock():
    event, actor, repo, storage, crews = setup(EventStatus.SETTLED)
    with pytest.raises(ValidationError):
        await RegisterEventExtensionUseCase(repo, storage, crews, FixedClock()).execute(
            extension_input(event.id, agreed_rate=Decimal("0")), actor
        )
    assert repo.loads == storage.paths == []
    assert repo.locks == 0


async def test_evidence_precedes_database_lock_and_conflict_is_compensated():
    event, actor, repo, storage, crews = setup()

    async def load(event_id):
        assert storage.paths
        raise EventResourceConflictError("Recursos no disponibles")

    repo.get_by_id_for_update = load
    with pytest.raises(EventResourceConflictError):
        await RegisterEventExtensionUseCase(repo, storage, crews, FixedClock()).execute(
            extension_input(event.id), actor
        )
    assert storage.deleted == storage.paths
    assert repo.saves == []


async def test_uncertain_commit_keeps_evidence_when_database_cannot_be_queried():
    event, actor, repo, storage, crews = setup()
    repo.fail_save = True

    async def unavailable(payment_id):
        raise ConnectionError("database unavailable")

    repo.can_discard_extension_evidence = unavailable
    with pytest.raises(RuntimeError, match="persistir"):
        await RegisterEventExtensionUseCase(repo, storage, crews, FixedClock()).execute(
            extension_input(event.id), actor
        )
    assert storage.paths
    assert storage.deleted == []


async def test_internal_unrecognized_role_has_explicit_forbidden_error():
    from types import SimpleNamespace

    from app.application.use_cases.event.access_errors import EventRoleForbiddenError

    event, actor, repo, storage, crews = setup()
    actor = SimpleNamespace(user_id=actor.user_id, role="CLIENTE")
    with pytest.raises(EventRoleForbiddenError):
        await RegisterEventExtensionUseCase(repo, storage, crews, FixedClock()).execute(
            extension_input(event.id), actor
        )
    assert repo.loads == storage.paths == []
