"""Dobles en memoria de la deduplicación y la cola de eventos del gateway."""

from dataclasses import dataclass
from datetime import datetime


class InMemoryDedup:
    """Doble de ``IEventDedupPort``: guarda los ids y el TTL con que se reclamaron."""

    def __init__(self, *, fail_claim: bool = False, fail_release: bool = False) -> None:
        self.keys: dict[str, int] = {}
        self.released: list[str] = []
        self._fail_claim = fail_claim
        self._fail_release = fail_release

    async def claim(self, event_id: str, *, ttl_seconds: int) -> bool:
        if self._fail_claim:
            raise ConnectionError("redis caido")
        if event_id in self.keys:
            return False
        self.keys[event_id] = ttl_seconds
        return True

    async def release(self, event_id: str) -> None:
        if self._fail_release:
            raise ConnectionError("redis caido")
        self.released.append(event_id)
        self.keys.pop(event_id, None)


@dataclass(frozen=True)
class Queued:
    event_id: str
    raw_body: bytes
    received_at: datetime


class RecordingQueue:
    """Doble de ``IGatewayEventQueuePort``; puede fallar al encolar."""

    def __init__(self, *, fail: bool = False) -> None:
        self.jobs: list[Queued] = []
        self._fail = fail

    async def enqueue(self, *, event_id: str, raw_body: bytes, received_at: datetime) -> None:
        if self._fail:
            raise ConnectionError("pool caido")
        self.jobs.append(Queued(event_id, raw_body, received_at))
