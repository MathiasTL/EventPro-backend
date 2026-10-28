"""Límites por IP de las cinco rutas públicas de firma, con almacenamiento en memoria."""

import pytest
from limits.storage import MemoryStorage

from tests.rate_limit_support import (
    OTP_REQUEST,
    OTP_VERIFY,
    PDF,
    SIGN,
    SIGNING_ENDPOINTS,
    VIEW,
    SigningEndpoint,
    assert_blocked_after_limit,
    bind_storage,
    call,
    exhaust,
    signing_app,
    signing_client,
    token,
)


@pytest.fixture(autouse=True)
def _memory_limiter(monkeypatch: pytest.MonkeyPatch) -> None:
    bind_storage(monkeypatch, MemoryStorage())


@pytest.mark.parametrize("endpoint", [OTP_REQUEST, OTP_VERIFY, SIGN], ids=lambda e: e.name)
async def test_post_limit_is_shared_across_tokens_per_ip(endpoint: SigningEndpoint) -> None:
    app, _ = signing_app()

    await assert_blocked_after_limit(app, endpoint)


async def test_view_and_pdf_share_one_limit_per_ip() -> None:
    app, _ = signing_app()

    async with signing_client(app, "192.0.2.20") as client:
        await exhaust(client, VIEW, 15)
        await exhaust(client, PDF, 15)
        blocked_view = await call(client, VIEW, token("z"))
        blocked_pdf = await call(client, PDF, token("z"))

    assert blocked_view.status_code == 429
    assert blocked_pdf.status_code == 429
    assert VIEW.limit == PDF.limit == 30


async def test_each_reading_route_can_reach_the_shared_limit_alone() -> None:
    app, _ = signing_app()

    await assert_blocked_after_limit(app, PDF)


@pytest.mark.parametrize("exhausted", SIGNING_ENDPOINTS, ids=lambda e: e.name)
async def test_exhausting_one_scope_leaves_the_others_available(
    exhausted: SigningEndpoint,
) -> None:
    app, _ = signing_app()
    shares_scope = {exhausted.name} | ({"view", "pdf"} if exhausted in (VIEW, PDF) else set())

    async with signing_client(app, "192.0.2.20") as client:
        await exhaust(client, exhausted, exhausted.limit)
        for other in SIGNING_ENDPOINTS:
            expected = 429 if other.name in shares_scope else other.status
            assert (await call(client, other, token("z"))).status_code == expected, other.name
