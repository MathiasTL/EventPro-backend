"""Los límites por IP dependen de que Uvicorn confíe en Caddy y en nadie más."""

import re
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI, Request
from slowapi.util import get_remote_address
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

PROXY_COMPOSE = Path(__file__).resolve().parents[2] / "docker-compose.proxy.yml"
CADDY_IP = "172.18.0.6"


def _compose_forwarded_allow_ips() -> str:
    match = re.search(r'^\s+FORWARDED_ALLOW_IPS:\s*"?([^"\s#]+)"?', PROXY_COMPOSE.read_text(), re.M)
    assert match, "docker-compose.proxy.yml debe definir FORWARDED_ALLOW_IPS para la API"
    return match.group(1)


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/ip")
    async def ip(request: Request) -> dict[str, str]:
        return {"ip": get_remote_address(request)}

    return app


async def _seen_ip(peer: str, forwarded_for: str) -> str:
    trusted = ProxyHeadersMiddleware(_app(), trusted_hosts=_compose_forwarded_allow_ips())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(trusted, client=(peer, 4321)), base_url="http://test"
    ) as client:
        response = await client.get("/ip", headers={"X-Forwarded-For": forwarded_for})
    return response.json()["ip"]


def test_compose_trusts_only_the_private_docker_range() -> None:
    assert _compose_forwarded_allow_ips() == "172.16.0.0/12"


async def test_forwarded_for_from_caddy_is_the_client_ip() -> None:
    assert await _seen_ip(CADDY_IP, "203.0.113.9") == "203.0.113.9"


async def test_client_supplied_prefix_cannot_spoof_the_ip() -> None:
    assert await _seen_ip(CADDY_IP, "6.6.6.6, 203.0.113.9") == "203.0.113.9"


@pytest.mark.parametrize("peer", ["203.0.113.50", "172.32.0.1", "192.168.1.5"])
async def test_forwarded_for_from_an_untrusted_peer_is_ignored(peer: str) -> None:
    assert await _seen_ip(peer, "6.6.6.6") == peer
