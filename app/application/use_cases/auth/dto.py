from dataclasses import dataclass
from uuid import UUID

from app.domain.value_objects.role import Role


@dataclass(frozen=True)
class UserInfo:
    id: UUID
    full_name: str
    role: Role


@dataclass(frozen=True)
class AuthSession:
    access_token: str
    refresh_token: str
    expires_in: int
    user: UserInfo | None = None
