"""Soporte para probar los límites por IP del enlace de firma sin Redis ni envío real de OTP.

El ``limiter`` de slowapi es un singleton de módulo ya enlazado a los decoradores de las rutas,
así que no se puede sustituir por una instancia nueva: la única vía para aislar el
almacenamiento es reenlazar sus atributos internos, y se hace aquí, en un solo lugar.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from limits.strategies import FixedWindowRateLimiter

from app.application.use_cases.contract.sign_contract import SignatureError
from app.infrastructure.adapters.primary.web.rate_limit import limiter
from app.infrastructure.adapters.secondary.persistence.database import get_contract_write_session
from app.infrastructure.di.containers import get_sign_contract_use_case
from app.main import create_app

SIGN_PATH = "/api/v1/contracts/sign/"


def bind_storage(monkeypatch: pytest.MonkeyPatch, storage: Any) -> None:
    """Hace que el ``limiter`` global use ``storage`` hasta que termine el test."""
    # Atributos privados de slowapi: no existe API pública para cambiar el almacenamiento.
    monkeypatch.setattr(limiter, "_storage", storage)
    monkeypatch.setattr(limiter, "_limiter", FixedWindowRateLimiter(storage))
    monkeypatch.setattr(limiter, "_storage_dead", False)


@dataclass(frozen=True)
class SigningEndpoint:
    """Una ruta pública de firma, el límite esperado y el estado que devuelve sin limitar."""

    name: str
    method: str
    suffix: str
    limit: int
    status: int
    json: dict[str, Any] | None = None

    def path(self, token: str) -> str:
        return f"{SIGN_PATH}{token}{self.suffix}"


_SIGN_BODY = {
    "otp_proof": "p" * 24,
    # Base64 inválido: la ruta responde 422 tras consumir el límite, sin firmar nada.
    "signature_base64": "###",
    "signer_full_name": "Cliente Prueba",
    "accept_terms": True,
}

VIEW = SigningEndpoint("view", "GET", "", 30, 404)
PDF = SigningEndpoint("pdf", "GET", "/pdf", 30, 404)
OTP_REQUEST = SigningEndpoint("otp-request", "POST", "/otp", 10, 200)
OTP_VERIFY = SigningEndpoint("otp-verify", "POST", "/otp/verify", 20, 200, {"otp_code": "123456"})
SIGN = SigningEndpoint("sign", "POST", "", 10, 422, _SIGN_BODY)
SIGNING_ENDPOINTS = (VIEW, PDF, OTP_REQUEST, OTP_VERIFY, SIGN)


def signing_app() -> tuple[FastAPI, SimpleNamespace]:
    """App con el caso de uso y la transacción sustituidos por dobles."""
    missing = SignatureError(404, "signature-link-invalid", "Enlace no válido")
    service = SimpleNamespace(
        resolve=AsyncMock(side_effect=missing),
        pdf=AsyncMock(side_effect=missing),
        request_otp=AsyncMock(return_value={"otp_sent": True}),
        verify_otp=AsyncMock(return_value={"otp_verified": True}),
        sign=AsyncMock(),
    )

    async def transaction() -> AsyncIterator[None]:
        yield None

    app = create_app()
    app.dependency_overrides[get_sign_contract_use_case] = lambda: service
    app.dependency_overrides[get_contract_write_session] = transaction
    return app, service


def signing_client(app: FastAPI, ip: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app, client=(ip, 1234)), base_url="http://test"
    )


def token(letter: str) -> str:
    return letter * 40


async def call(client: httpx.AsyncClient, endpoint: SigningEndpoint, tok: str) -> httpx.Response:
    return await client.request(endpoint.method, endpoint.path(tok), json=endpoint.json)


async def exhaust(client: httpx.AsyncClient, endpoint: SigningEndpoint, count: int) -> None:
    """Consume ``count`` peticiones, cada una con un token distinto, y exige que pasen."""
    for index in range(count):
        response = await call(client, endpoint, f"{index:040d}")
        assert response.status_code == endpoint.status, (endpoint.name, index, response.text)


async def assert_blocked_after_limit(app: FastAPI, endpoint: SigningEndpoint) -> None:
    """El límite se agota por IP aunque cambie el token y no afecta a otra IP."""
    async with signing_client(app, "192.0.2.20") as client:
        await exhaust(client, endpoint, endpoint.limit)
        blocked = await call(client, endpoint, token("z"))
    assert blocked.status_code == 429, endpoint.name
    assert blocked.json()["type"].endswith("/rate-limit-exceeded")
    assert "Retry-After" in blocked.headers
    async with signing_client(app, "192.0.2.21") as other:
        assert (await call(other, endpoint, token("z"))).status_code == endpoint.status
