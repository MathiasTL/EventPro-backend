"""Pruebas unitarias de ManageCrewsUseCase (RF-29, US-26)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.dtos.catalog_dto import CrewDTO
from app.application.use_cases.crew.manage_crews import ManageCrewsUseCase
from app.domain.entities.user import User
from app.domain.exceptions.resource_exceptions import (
    DuplicateResourceError,
    ResourceNotFoundError,
    ValidationError,
)
from app.domain.value_objects.role import Role
from app.domain.value_objects.service_category import ServiceCategory


def _user(role: Role) -> User:
    return User(
        id=uuid4(),
        full_name="Operador Uno",
        email="operador@eventpro.pe",
        phone="+51999000111",
        role=role,
        hashed_password="hash",
    )


def _use_case() -> tuple[ManageCrewsUseCase, AsyncMock, AsyncMock]:
    crews = AsyncMock()
    users = AsyncMock()
    return ManageCrewsUseCase(crews, users), crews, users


def test_create_crew_without_user() -> None:
    use_case, crews, _users = _use_case()
    result = asyncio.run(
        use_case.create_crew(
            leader_name="Luis Torres",
            phone="+51955666777",
            service_category=ServiceCategory.SHOW,
        )
    )
    assert result is crews.create_crew.return_value
    crews.create_crew.assert_awaited_once()


def test_create_crew_rejects_non_operator_user() -> None:
    use_case, crews, users = _use_case()
    users.get_by_id.return_value = _user(Role.ENCARGADO)
    with pytest.raises(ValidationError):
        asyncio.run(
            use_case.create_crew(
                leader_name="Luis Torres",
                phone="+51955666777",
                service_category=ServiceCategory.SHOW,
                user_id=uuid4(),
            )
        )
    crews.create_crew.assert_not_awaited()


def test_create_crew_rejects_unknown_user() -> None:
    use_case, crews, users = _use_case()
    users.get_by_id.return_value = None
    with pytest.raises(ResourceNotFoundError):
        asyncio.run(
            use_case.create_crew(
                leader_name="Luis Torres",
                phone="+51955666777",
                service_category=ServiceCategory.SHOW,
                user_id=uuid4(),
            )
        )
    crews.create_crew.assert_not_awaited()


def test_create_crew_rejects_user_already_linked() -> None:
    use_case, crews, users = _use_case()
    users.get_by_id.return_value = _user(Role.OPERADOR)
    crews.find_crew_by_user.return_value = CrewDTO(
        id=uuid4(),
        leader_name="Otro elenco",
        phone="+51911111111",
        service_category=ServiceCategory.DJ,
    )
    with pytest.raises(DuplicateResourceError):
        asyncio.run(
            use_case.create_crew(
                leader_name="Luis Torres",
                phone="+51955666777",
                service_category=ServiceCategory.SHOW,
                user_id=uuid4(),
            )
        )
    crews.create_crew.assert_not_awaited()


def test_update_crew_allows_same_crew_user() -> None:
    use_case, crews, users = _use_case()
    crew_id = uuid4()
    users.get_by_id.return_value = _user(Role.OPERADOR)
    crews.get_crew.return_value = CrewDTO(
        id=crew_id,
        leader_name="Luis Torres",
        phone="+51955666777",
        service_category=ServiceCategory.SHOW,
    )
    crews.find_crew_by_user.return_value = CrewDTO(
        id=crew_id,
        leader_name="Luis Torres",
        phone="+51955666777",
        service_category=ServiceCategory.SHOW,
    )
    result = asyncio.run(
        use_case.update_crew(
            crew_id,
            leader_name="Luis Torres",
            phone="+51955666777",
            service_category=ServiceCategory.SHOW,
            user_id=uuid4(),
        )
    )
    assert result is crews.update_crew.return_value


@pytest.mark.parametrize(
    ("is_active", "expected"),
    [(None, False), (True, True), (False, False)],
)
def test_patch_crew_preserves_or_explicitly_changes_status(
    is_active: bool | None, expected: bool
) -> None:
    use_case, crews, _users = _use_case()
    crew_id = uuid4()
    crews.get_crew.return_value = CrewDTO(
        id=crew_id,
        leader_name="Elenco inactivo",
        phone="+51955666777",
        service_category=ServiceCategory.SHOW,
        is_active=False,
    )

    asyncio.run(use_case.update_crew(crew_id, phone="+51911111111", is_active=is_active))

    updated = crews.update_crew.await_args.args[0]
    assert updated.is_active is expected
    assert updated.phone == "+51911111111"
    assert updated.leader_name == "Elenco inactivo"


def test_patch_crew_can_unlink_user_explicitly() -> None:
    use_case, crews, _users = _use_case()
    crew_id = uuid4()
    crews.get_crew.return_value = CrewDTO(
        id=crew_id,
        leader_name="Elenco",
        phone="+51955666777",
        service_category=ServiceCategory.SHOW,
        user_id=uuid4(),
    )

    asyncio.run(use_case.update_crew(crew_id, user_id=None, user_id_provided=True))

    assert crews.update_crew.await_args.args[0].user_id is None


def test_get_crew_missing_raises() -> None:
    use_case, crews, _users = _use_case()
    crews.get_crew.return_value = None
    with pytest.raises(ResourceNotFoundError):
        asyncio.run(use_case.get_crew(uuid4()))
