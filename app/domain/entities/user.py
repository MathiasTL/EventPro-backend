from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from app.domain.value_objects.role import Role


@dataclass
class User:
    id: UUID
    full_name: str
    email: str
    phone: str
    role: Role
    hashed_password: str
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
