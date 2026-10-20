"""POST /api/v1/webhooks/chatwoot: firma, deduplicación, encolado y fallas, sin JWT."""

import hashlib
import hmac
import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from structlog.testing import capture_logs

from app.application.use_cases.messaging.receive_gateway_event import ReceiveGatewayEvent
from app.core.config import Settings, get_settings
from app.infrastructure.di import containers
from app.main import create_app
from tests.application.gateway_event_support import InMemoryDedup, RecordingQueue
from tests.chatwoot_fixture_support import load_fixture

PATH = "/api/v1/webhooks/chatwoot"
SECRET = "secreto-de-prueba"
NOW = datetime(2026, 10, 12, 14, 1, 0, tzinfo=UTC)
BODY = json.dumps(load_fixture("message_updated_delivered")["body"], separators=(",", ":")).encode()
DELIVERY = "00000000-0000-4000-8000-000000000001"


class FixedClock:
    def utcnow(self) -> datetime:
        return NOW


@dataclass
class Harness:
    app: FastAPI
    dedup: InMemoryDedup
    queue: RecordingQueue


def make_harness(
    *, secret: str = SECRET, dedup: InMemoryDedup | None = None, queue: RecordingQueue | None = None
) -> Harness:
    dedup = dedup or InMemoryDedup()
    queue = queue or RecordingQueue()
    app = create_app()
    settings = Settings(secret_key="s" * 40, chatwoot_webhook_secret=SecretStr(secret))
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[containers.get_clock_port] = FixedClock
    use_case = ReceiveGatewayEvent(dedup, queue)
    app.dependency_overrides[containers.get_receive_gateway_event_use_case] = lambda: use_case
    return Harness(app, dedup, queue)


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("SECRET_KEY", "s" * 40)
    yield


@pytest.fixture
def harness() -> Harness:
    return make_harness()


def sign(body: bytes, timestamp: str, *, secret: str = SECRET) -> str:
    message = timestamp.encode() + b"." + body
    return "sha256=" + hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def stamp(offset_seconds: int = 0) -> str:
    return str(int((NOW + timedelta(seconds=offset_seconds)).timestamp()))


def signed_headers(
    body: bytes = BODY, *, offset: int = 0, delivery: str | None = DELIVERY
) -> dict[str, str]:
    timestamp = stamp(offset)
    headers = {
        "Content-Type": "application/json",
        "X-Chatwoot-Timestamp": timestamp,
        "X-Chatwoot-Signature": sign(body, timestamp),
    }
    if delivery is not None:
        headers["X-Chatwoot-Delivery"] = delivery
    return headers


async def post(
    app: FastAPI, body: bytes = BODY, headers: dict[str, str] | None = None
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(
            PATH, content=body, headers=signed_headers(body) if headers is None else headers
        )


# --- Aceptación -----------------------------------------------------------------------------


async def test_a_valid_signed_request_is_acknowledged_and_enqueued_without_authorization(
    harness: Harness,
) -> None:
    response = await post(harness.app)

    assert response.status_code == 200
    assert response.json() == {"status": "EVENT_RECEIVED"}
    assert "authorization" not in response.request.headers
    assert [job.event_id for job in harness.queue.jobs] == [DELIVERY]


async def test_the_raw_bytes_reach_the_queue_unmodified(harness: Harness) -> None:
    odd = b'{ "event" :"message_updated",\n  "id":6 }'

    response = await post(harness.app, odd, signed_headers(odd))

    assert response.status_code == 200
    assert harness.queue.jobs[0].raw_body == odd


async def test_received_at_is_the_instant_of_the_verified_timestamp_header(
    harness: Harness,
) -> None:
    response = await post(harness.app, BODY, signed_headers(offset=-250))

    assert response.status_code == 200
    assert harness.queue.jobs[0].received_at == NOW - timedelta(seconds=250)
    assert harness.queue.jobs[0].received_at.tzinfo is UTC


async def test_the_response_is_returned_after_the_event_is_queued_not_processed(
    harness: Harness,
) -> None:
    response = await post(harness.app)

    # El único efecto antes de responder es dejar el trabajo en la cola; no hay lectura de BD.
    assert response.status_code == 200
    assert len(harness.queue.jobs) == 1
    assert harness.dedup.keys == {DELIVERY: 604_800}


@pytest.mark.parametrize(("offset", "status"), [(-299, 200), (-300, 200), (-301, 401), (301, 401)])
async def test_the_five_minute_window_uses_the_injected_clock(
    harness: Harness, offset: int, status: int
) -> None:
    response = await post(harness.app, BODY, signed_headers(offset=offset))

    assert response.status_code == status


# --- Rechazo --------------------------------------------------------------------------------


def _without(headers: dict[str, str], name: str) -> dict[str, str]:
    return {key: value for key, value in headers.items() if key != name}


def _rejections() -> list[tuple[str, bytes, dict[str, str], str]]:
    good = signed_headers()
    pretty = json.dumps(json.loads(BODY), indent=2).encode()
    return [
        ("no-signature", BODY, _without(good, "X-Chatwoot-Signature"), "missing_header"),
        ("no-timestamp", BODY, _without(good, "X-Chatwoot-Timestamp"), "missing_header"),
        (
            "wrong-hmac",
            BODY,
            {**good, "X-Chatwoot-Signature": sign(BODY, stamp(), secret="otro")},
            "mismatch",
        ),
        (
            "altered-body",
            BODY.replace(b'"event":"message_updated"', b'"event":"message_created"'),
            good,
            "mismatch",
        ),
        ("pretty-body", pretty, good, "mismatch"),
        (
            "bad-timestamp",
            BODY,
            {**good, "X-Chatwoot-Timestamp": "abc", "X-Chatwoot-Signature": sign(BODY, "abc")},
            "bad_timestamp",
        ),
        (
            "no-prefix",
            BODY,
            {**good, "X-Chatwoot-Signature": good["X-Chatwoot-Signature"].removeprefix("sha256=")},
            "mismatch",
        ),
        ("stale", BODY, signed_headers(offset=-301), "stale_timestamp"),
    ]


@pytest.mark.parametrize(
    ("body", "headers", "reason"),
    [pytest.param(b, h, r, id=i) for i, b, h, r in _rejections()],
)
async def test_every_signature_failure_is_a_401_problem_that_enqueues_and_claims_nothing(
    harness: Harness, body: bytes, headers: dict[str, str], reason: str
) -> None:
    with capture_logs() as logs:
        response = await post(harness.app, body, headers)

    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"
    problem = response.json()
    assert problem["type"] == "https://errors.eventpro.pe/invalid-webhook-signature"
    assert (problem["status"], problem["title"], problem["instance"]) == (
        401,
        "No autorizado",
        PATH,
    )
    assert harness.queue.jobs == []
    assert harness.dedup.keys == {}
    assert logs == [
        {"event": "chatwoot_webhook_rejected", "log_level": "warning", "reason": reason}
    ]


async def test_the_rejection_response_and_log_leak_neither_the_secret_nor_the_signature() -> None:
    harness = make_harness()
    headers = signed_headers()
    headers["X-Chatwoot-Signature"] = sign(BODY, stamp(), secret="otro")

    with capture_logs() as logs:
        response = await post(harness.app, BODY, headers)

    assert response.status_code == 401
    assert logs
    for leaked in (SECRET, headers["X-Chatwoot-Signature"], "wamid.FAKE0002"):
        assert leaked not in response.text
        assert leaked not in repr(logs)


async def test_with_the_secret_unset_every_request_is_rejected_even_if_well_formed() -> None:
    harness = make_harness(secret="")
    headers = signed_headers()
    headers["X-Chatwoot-Signature"] = sign(BODY, stamp(), secret="")

    with capture_logs() as logs:
        response = await post(harness.app, BODY, headers)

    assert response.status_code == 401
    assert harness.queue.jobs == []
    assert [log["reason"] for log in logs] == ["secret_not_configured"]


# --- Deduplicación --------------------------------------------------------------------------


async def test_a_duplicate_delivery_is_acknowledged_without_a_second_enqueue(
    harness: Harness,
) -> None:
    first = await post(harness.app)
    second = await post(harness.app, BODY, signed_headers(offset=-5))

    assert (first.status_code, second.status_code) == (200, 200)
    assert second.json() == {"status": "EVENT_RECEIVED"}
    assert len(harness.queue.jobs) == 1


async def test_identical_bodies_with_different_delivery_ids_are_both_enqueued(
    harness: Harness,
) -> None:
    await post(harness.app, BODY, signed_headers(delivery="delivery-a"))
    await post(harness.app, BODY, signed_headers(delivery="delivery-b"))

    assert [job.event_id for job in harness.queue.jobs] == ["delivery-a", "delivery-b"]


async def test_without_the_delivery_header_the_event_is_kept_with_the_signature_digest(
    harness: Harness,
) -> None:
    headers = signed_headers(delivery=None)
    digest = headers["X-Chatwoot-Signature"].removeprefix("sha256=")

    with capture_logs() as logs:
        response = await post(harness.app, BODY, headers)

    assert response.status_code == 200
    assert [job.event_id for job in harness.queue.jobs] == [digest]
    assert logs == [{"event": "chatwoot_webhook_delivery_id_missing", "log_level": "info"}]


async def test_an_empty_delivery_header_counts_as_absent(harness: Harness) -> None:
    headers = signed_headers(delivery="")
    digest = headers["X-Chatwoot-Signature"].removeprefix("sha256=")

    response = await post(harness.app, BODY, headers)

    assert response.status_code == 200
    assert [job.event_id for job in harness.queue.jobs] == [digest]


async def test_a_retransmission_without_the_delivery_header_is_deduplicated_by_the_digest(
    harness: Harness,
) -> None:
    headers = signed_headers(delivery=None)

    await post(harness.app, BODY, headers)
    await post(harness.app, BODY, headers)

    assert len(harness.queue.jobs) == 1


async def test_a_duplicate_is_logged_with_the_delivery_id_only(harness: Harness) -> None:
    await post(harness.app)

    with capture_logs() as logs:
        await post(harness.app)

    assert logs == [
        {"event": "chatwoot_webhook_duplicate", "log_level": "info", "event_id": DELIVERY}
    ]


# --- Falla de cola --------------------------------------------------------------------------


async def test_a_queue_failure_is_a_503_problem_and_the_key_is_released() -> None:
    harness = make_harness(queue=RecordingQueue(fail=True))

    with capture_logs() as logs:
        response = await post(harness.app)

    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    problem = response.json()
    assert problem["type"] == "https://errors.eventpro.pe/event-queue-unavailable"
    assert (problem["status"], problem["title"]) == (503, "Servicio no disponible")
    assert harness.dedup.keys == {}
    assert logs == [
        {
            "event": "gateway_event_not_queued",
            "log_level": "error",
            "event_id": DELIVERY,
            "error_type": "ConnectionError",
        }
    ]


async def test_a_resend_after_a_queue_failure_is_enqueued() -> None:
    dedup = InMemoryDedup()
    failing = make_harness(dedup=dedup, queue=RecordingQueue(fail=True))
    assert (await post(failing.app)).status_code == 503
    working = make_harness(dedup=dedup)

    response = await post(working.app)

    assert response.status_code == 200
    assert [job.event_id for job in working.queue.jobs] == [DELIVERY]


async def test_a_claim_failure_is_a_503_and_nothing_is_enqueued() -> None:
    harness = make_harness(dedup=InMemoryDedup(fail_claim=True))

    response = await post(harness.app)

    assert response.status_code == 503
    assert harness.queue.jobs == []


async def test_a_queue_failure_without_the_delivery_header_never_logs_the_signature() -> None:
    harness = make_harness(queue=RecordingQueue(fail=True))
    headers = signed_headers(delivery=None)
    digest = headers["X-Chatwoot-Signature"].removeprefix("sha256=")

    with capture_logs() as logs:
        response = await post(harness.app, BODY, headers)

    assert response.status_code == 503
    assert [log["event"] for log in logs] == [
        "chatwoot_webhook_delivery_id_missing",
        "gateway_event_not_queued",
    ]
    assert digest not in repr(logs)
    assert logs[1]["event_id"] == "signature-digest"
