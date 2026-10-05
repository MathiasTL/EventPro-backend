"""require_role(...) — dependencia reutilizable de autorización (Matriz RBAC §3.2)."""

import uuid

import pytest

from app.domain.value_objects.role import Role
from app.infrastructure.adapters.primary.web.deps import AuthContext, require_role
from app.infrastructure.adapters.primary.web.problem import ProblemError


def _context(role: Role) -> AuthContext:
    return AuthContext(user_id=uuid.uuid4(), role=role)


async def test_require_role_allows_listed_role() -> None:
    dependency = require_role(Role.SUPERADMIN, Role.ENCARGADO)

    context = await dependency(_context(Role.ENCARGADO))

    assert context.role == Role.ENCARGADO


async def test_require_role_forbids_other_role() -> None:
    dependency = require_role(Role.SUPERADMIN)

    with pytest.raises(ProblemError) as exc_info:
        await dependency(_context(Role.OPERADOR))

    problem = exc_info.value
    assert problem.status == 403
    assert problem.suffix == "forbidden"


def test_require_role_requires_at_least_one_role() -> None:
    with pytest.raises(ValueError):
        require_role()
