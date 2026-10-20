from datetime import UTC, datetime


class SystemClockAdapter:
    def utcnow(self) -> datetime:
        return datetime.now(UTC)
