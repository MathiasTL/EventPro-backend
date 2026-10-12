"""Recepción del webhook de Chatwoot sobre Redis real (Testcontainers).

Primera parte: el adaptador de deduplicación. Segunda: la ruta completa con firma, clave de
deduplicación y cola de arq reales (sin Chatwoot: el cuerpo es el fixture saneado).
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import time
from collections.abc import Iterator
from uuid import uuid4

import httpx
import pytest
from arq.jobs import Job
from fastapi import FastAPI
from pydantic import SecretStr

from app.core.config import Settings, get_settings
from app.infrastructure.adapters.secondary.cache.redis_event_dedup_adapter import (
    KEY_PREFIX,
    RedisEventDedupAdapter,
)
from app.infrastructure.adapters.secondary.queue.arq_gateway_event_queue import (
    GATEWAY_EVENT_DEFER_SECONDS,
    PROCESS_GATEWAY_EVENT_JOB,
)
from app.infrastructure.di import containers
from app.infrastructure.di.containers import get_arq_pool, get_redis_client
from app.main import create_app
from tests.chatwoot_fixture_support import load_fixture

pytestmark = pytest.mark.integration

TTL_SECONDS = 604_800


@pytest.fixture
def dedup(infra: None) -> RedisEventDedupAdapter:
    return RedisEventDedupAdapter(get_redis_client())


async def test_the_first_claim_stores_the_key_with_a_seven_day_ttl(
    dedup: RedisEventDedupAdapter,
) -> None:
    claimed = await dedup.claim("delivery-ttl", ttl_seconds=TTL_SECONDS)

    ttl = await get_redis_client().ttl(f"{KEY_PREFIX}delivery-ttl")
    assert claimed is True
    assert KEY_PREFIX == "eventpro:chatwoot:webhook:"
    assert TTL_SECONDS - 10 <= ttl <= TTL_SECONDS


async def test_a_second_claim_of_the_same_id_is_refused(dedup: RedisEventDedupAdapter) -> None:
    first = await dedup.claim("delivery-twice", ttl_seconds=TTL_SECONDS)
    second = await dedup.claim("delivery-twice", ttl_seconds=TTL_SECONDS)
    other = await dedup.claim("delivery-other", ttl_seconds=TTL_SECONDS)

    assert (first, second, other) == (True, False, True)


async def test_release_deletes_the_key_so_the_id_can_be_claimed_again(
    dedup: RedisEventDedupAdapter,
) -> None:
    await dedup.claim("delivery-release", ttl_seconds=TTL_SECONDS)

    await dedup.release("delivery-release")

    assert await get_redis_client().exists(f"{KEY_PREFIX}delivery-release") == 0
    assert await dedup.claim("delivery-release", ttl_seconds=TTL_SECONDS) is True


async def test_releasing_an_unknown_id_does_not_fail(dedup: RedisEventDedupAdapter) -> None:
    await dedup.release("delivery-never-claimed")


async def test_twenty_concurrent_claims_of_one_id_have_exactly_one_winner(
    dedup: RedisEventDedupAdapter,
) -> None:
    results = await asyncio.gather(
        *(dedup.claim("delivery-race", ttl_seconds=TTL_SECONDS) for _ in range(20))
    )

    assert results.count(True) == 1
    assert results.count(False) == 19


async def test_an_expired_key_is_treated_as_a_new_event(dedup: RedisEventDedupAdapter) -> None:
    assert await dedup.claim("delivery-expiry", ttl_seconds=1) is True
    assert await dedup.claim("delivery-expiry", ttl_seconds=1) is False

    await asyncio.sleep(1.2)

    assert await dedup.claim("delivery-expiry", ttl_seconds=1) is True


# --- Ruta completa ----------------------------------------------------------------------------

PATH = "/api/v1/webhooks/chatwoot"
SECRET = "secreto-de-integracion"
ARQ_QUEUE = "arq:queue"
BODY = json.dumps(load_fixture("message_updated_delivered")["body"], separators=(",", ":")).encode()


def _headers(delivery: str, *, body: bytes = BODY) -> dict[str, str]:
    timestamp = str(int(time.time()))
    digest = hmac.new(SECRET.encode(), timestamp.encode() + b"." + body, hashlib.sha256)
    return {
        "Content-Type": "application/json",
        "X-Chatwoot-Timestamp": timestamp,
        "X-Chatwoot-Signature": f"sha256={digest.hexdigest()}",
        "X-Chatwoot-Delivery": delivery,
    }


@pytest.fixture
def webhook_app(infra: None) -> Iterator[FastAPI]:
    app = create_app()
    settings = Settings(secret_key="s" * 40, chatwoot_webhook_secret=SecretStr(SECRET))
    app.dependency_overrides[get_settings] = lambda: settings
    yield app


@pytest.fixture
async def clean_queue(infra: None) -> None:
    redis = get_redis_client()
    await redis.delete(ARQ_QUEUE)
    for key in await redis.keys("arq:job:chatwoot:*"):
        await redis.delete(key)


async def _post(app: FastAPI, headers: dict[str, str], body: bytes = BODY) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(PATH, content=body, headers=headers)


@pytest.mark.usefixtures("clean_queue")
async def test_a_signed_fixture_stores_the_key_and_queues_exactly_one_deferred_job(
    webhook_app: FastAPI,
) -> None:
    delivery = f"delivery-{uuid4()}"

    response = await _post(webhook_app, _headers(delivery))

    redis = get_redis_client()
    assert response.status_code == 200
    assert response.json() == {"status": "EVENT_RECEIVED"}
    ttl = await redis.ttl(f"{KEY_PREFIX}{delivery}")
    assert 604_800 - 10 <= ttl <= 604_800
    queued = await redis.zrange(ARQ_QUEUE, 0, -1, withscores=True)
    assert [member for member, _ in queued] == [f"chatwoot:{delivery}".encode()]
    # El trabajo espera unos segundos: su puntaje (ms) está en el futuro.
    assert queued[0][1] > time.time() * 1000 + (GATEWAY_EVENT_DEFER_SECONDS - 1) * 1000
    info = await Job(f"chatwoot:{delivery}", get_arq_pool()).info()
    assert info is not None
    assert info.function == PROCESS_GATEWAY_EVENT_JOB
    received_at_epoch = int(_headers(delivery)["X-Chatwoot-Timestamp"])
    assert info.args[0] == BODY
    assert abs(info.args[1] - received_at_epoch) <= 5


@pytest.mark.usefixtures("clean_queue")
async def test_the_same_delivery_id_again_adds_no_job(webhook_app: FastAPI) -> None:
    delivery = f"delivery-{uuid4()}"
    await _post(webhook_app, _headers(delivery))

    again = await _post(webhook_app, _headers(delivery))

    assert again.status_code == 200
    assert await get_redis_client().zcard(ARQ_QUEUE) == 1


@pytest.mark.usefixtures("clean_queue")
async def test_two_deliveries_with_identical_bodies_queue_two_jobs(webhook_app: FastAPI) -> None:
    await _post(webhook_app, _headers(f"delivery-{uuid4()}"))
    await _post(webhook_app, _headers(f"delivery-{uuid4()}"))

    assert await get_redis_client().zcard(ARQ_QUEUE) == 2


@pytest.mark.usefixtures("clean_queue")
async def test_simultaneous_requests_with_one_delivery_id_queue_exactly_one_job(
    webhook_app: FastAPI,
) -> None:
    delivery = f"delivery-{uuid4()}"

    responses = await asyncio.gather(*(_post(webhook_app, _headers(delivery)) for _ in range(8)))

    assert [response.status_code for response in responses] == [200] * 8
    assert await get_redis_client().zcard(ARQ_QUEUE) == 1


@pytest.mark.usefixtures("clean_queue")
async def test_a_bad_signature_touches_neither_the_key_nor_the_queue(
    webhook_app: FastAPI,
) -> None:
    delivery = f"delivery-{uuid4()}"
    headers = _headers(delivery)
    headers["X-Chatwoot-Signature"] = "sha256=" + "0" * 64

    response = await _post(webhook_app, headers)

    redis = get_redis_client()
    assert response.status_code == 401
    assert await redis.exists(f"{KEY_PREFIX}{delivery}") == 0
    assert await redis.zcard(ARQ_QUEUE) == 0


@pytest.mark.usefixtures("clean_queue")
async def test_a_redis_outage_answers_503_and_leaves_no_key(webhook_app: FastAPI) -> None:
    delivery = f"delivery-{uuid4()}"
    headers = _headers(delivery)
    real_port = os.environ["REDIS_PORT"]
    os.environ["REDIS_PORT"] = "1"
    get_settings.cache_clear()
    get_redis_client.cache_clear()
    containers.clear_application_caches()
    try:
        response = await _post(webhook_app, headers)
    finally:
        os.environ["REDIS_PORT"] = real_port
        get_settings.cache_clear()
        get_redis_client.cache_clear()
        containers.clear_application_caches()

    assert response.status_code == 503
    assert response.json()["type"] == "https://errors.eventpro.pe/event-queue-unavailable"
    assert await get_redis_client().exists(f"{KEY_PREFIX}{delivery}") == 0
    assert await get_redis_client().zcard(ARQ_QUEUE) == 0
