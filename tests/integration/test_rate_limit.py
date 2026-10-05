"""Límite de tasa del login: 5 intentos por minuto por IP (spec §2.1)."""

import httpx
from httpx import ASGITransport

from app.main import app


async def _login_wrong_password() -> httpx.Response:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(
            "/auth/login",
            json={"email": "nadie@eventpro.pe", "password": "WrongPass123!"},
        )


async def test_login_rate_limit_after_five_attempts(infra: None) -> None:
    for _ in range(5):
        response = await _login_wrong_password()
        assert response.status_code == 401

    blocked = await _login_wrong_password()

    assert blocked.status_code == 429
    assert blocked.headers["content-type"].startswith("application/problem+json")
    assert "Retry-After" in blocked.headers
    body = blocked.json()
    assert body["type"] == "https://errors.eventpro.pe/rate-limit-exceeded"
    assert body["status"] == 429
    assert body["instance"] == "/auth/login"


async def test_rate_limit_resets_between_tests(infra: None) -> None:
    response = await _login_wrong_password()
    assert response.status_code == 401
