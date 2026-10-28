"""HTTP rate limiting with isolated storage; no Redis or real OTP delivery."""

from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter

from app.infrastructure.adapters.primary.web.rate_limit import limiter
from app.infrastructure.adapters.secondary.persistence.database import get_contract_write_session
from app.infrastructure.di.containers import get_sign_contract_use_case
from app.main import create_app


async def test_otp_verification_blocks_request_21_per_ip(monkeypatch):
    await assert_otp_limit(monkeypatch, MemoryStorage())


async def assert_otp_limit(monkeypatch, storage):
    monkeypatch.setattr(limiter, "_storage", storage)
    monkeypatch.setattr(limiter, "_limiter", FixedWindowRateLimiter(storage))
    monkeypatch.setattr(limiter, "_storage_dead", False)
    service = SimpleNamespace(verify_otp=AsyncMock(return_value={"otp_verified": True}))

    async def transaction() -> AsyncIterator[None]:
        yield None

    app = create_app()
    app.dependency_overrides[get_sign_contract_use_case] = lambda: service
    app.dependency_overrides[get_contract_write_session] = transaction
    path = "/api/v1/contracts/sign/" + "a" * 40 + "/otp/verify"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app, client=("192.0.2.20", 1234)),
        base_url="http://test",
    ) as client:
        for _ in range(20):
            response = await client.post(path, json={"otp_code": "123456"})
            assert response.status_code == 200
        # Another contract must share the same IP limit.
        blocked = await client.post(path.replace("a" * 40, "b" * 40), json={"otp_code": "123456"})
    assert blocked.status_code == 429
    assert blocked.json()["type"].endswith("/rate-limit-exceeded")
    assert "Retry-After" in blocked.headers
    assert service.verify_otp.await_count == 20
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app, client=("192.0.2.21", 1234)),
        base_url="http://test",
    ) as other_client:
        assert (await other_client.post(path, json={"otp_code": "123456"})).status_code == 200
