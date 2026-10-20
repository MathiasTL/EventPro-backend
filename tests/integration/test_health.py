import os

import httpx
from httpx import ASGITransport

from app.core.config import get_settings
from app.main import app


async def _get(path: str) -> httpx.Response:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


async def test_health_ok(infra: None) -> None:
    response = await _get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": "ok", "redis": "ok"},
    }


async def test_health_serves_security_headers(infra: None) -> None:
    response = await _get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Strict-Transport-Security"].startswith("max-age=31536000")


async def test_health_degraded_when_redis_down(infra: None) -> None:
    from app.infrastructure.di.containers import get_cache_port, get_redis_client

    original_port = os.environ.get("REDIS_PORT")
    os.environ["REDIS_PORT"] = "1"
    get_settings.cache_clear()
    get_redis_client.cache_clear()
    get_cache_port.cache_clear()
    try:
        response = await _get("/health")
    finally:
        if original_port is None:
            os.environ.pop("REDIS_PORT", None)
        else:
            os.environ["REDIS_PORT"] = original_port
        get_settings.cache_clear()
        get_redis_client.cache_clear()
        get_cache_port.cache_clear()

    assert response.status_code == 503
    assert response.json() == {
        "status": "degraded",
        "checks": {"database": "ok", "redis": "error"},
    }
