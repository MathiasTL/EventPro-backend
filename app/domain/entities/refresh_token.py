from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID


@dataclass
class RefreshToken:
    id: UUID
    user_id: UUID
    token_hash: str
    expires_at: datetime
    is_revoked: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def is_valid(self, now: datetime) -> bool:
        return not self.is_revoked and now < self.expires_at

    def revoke(self) -> None:
        self.is_revoked = True
